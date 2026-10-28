from fastapi import APIRouter, Depends, Request, Response, Query
from fastapi.responses import FileResponse
from sqlalchemy import select, update, text, func, or_
from datetime import datetime, timedelta, timezone
import hashlib
import os
from cryptography.fernet import InvalidToken
from ..schemas import CameraCreate, SourcePatch, SourceDTO, SourcePage, UploadCreate, UploadComplete, UploadDTO, SourceTestDTO, PreviewDTO
from ..shared.models import Source, Upload, Job, Notification, Log, now, uid
from ..shared.db import get_db
from ..shared.errors import Error
from ..shared.security import camera_address
from ..shared.storage import controlled_path
from .settings import values_for

router = APIRouter(tags=['sources'])

def source_dto(source):
    dto = SourceDTO.model_validate(source)
    if source.status == 'ready' and source.media_key:
        dto.preview_url = f'/api/v1/sources/{source.id}/media'
    if source.thumbnail_key:
        dto.thumbnail_url = f'/api/v1/sources/{source.id}/thumbnail'
    return dto

def notify_source(db,source):
    db.add(Notification(type='source',aggregate_id=source.id,payload=source_dto(source).model_dump()))

def get_source(db,source_id):
    source = db.get(Source,source_id)
    if not source or source.archived:
        raise Error(404,'source_not_found','视频源不存在或已归档。')
    return source


def resolve_agent_source(db, source_id, allow_archived=False):
    """Public, read-only source reference for agent draft configuration (no credentials)."""
    source = db.get(Source, source_id)
    if source is None or (source.archived and not allow_archived):
        raise Error(422, 'source_unavailable', '所选视频源不存在或已归档，请重新选择。')
    return source_dto(source)


def resolve_execution_input(db, config, source_id, gateway):
    """Source-owned local decoder input; credentials and arbitrary paths never cross this port."""
    source = get_source(db, source_id)
    if source.kind == 'file':
        if source.status != 'ready' or not source.media_key:
            raise Error(422, 'source_not_ready', '录像尚未完成处理，暂不能开始监测。')
        path = controlled_path(config, 'media', source.media_key)
        if not path.is_file():
            raise Error(422, 'source_media_missing', '录像文件不可用，请重新上传。')
        locator = str(path)
    else:
        if source.status != 'online':
            raise Error(422, 'source_not_ready', '摄像头尚未验证在线，请先测试连接。')
        path = gateway.ensure_published(source, values_for(db, 'security')['camera_allowed_networks'])
        locator = f'rtsp://127.0.0.1:{config.media_gateway_rtsp_port}/{path}'
    return source_dto(source), locator

def get_upload(db,upload_id):
    upload = db.get(Upload,upload_id)
    if not upload:
        raise Error(404,'upload_not_found','上传记录不存在。')
    return upload

@router.get('/sources',response_model=SourcePage)
def list_sources(q:str='',kind:str|None=None,status:str|None=None,limit:int=Query(100,ge=1,le=500),cursor:str|None=None,db=Depends(get_db)):
    statement = select(Source).where(Source.archived==False)
    if q:
        statement = statement.where(or_(Source.name.contains(q,autoescape=True),Source.address.contains(q,autoescape=True)))
    if kind:
        statement = statement.where(Source.kind==kind)
    if status:
        statement = statement.where(Source.status==status)
    if cursor:
        statement = statement.where(Source.id>cursor)
    rows = list(db.scalars(statement.order_by(Source.id).limit(limit+1)))
    return {'items':[source_dto(row) for row in rows[:limit]],'next_cursor':rows[limit-1].id if len(rows)>limit else None}

@router.post('/sources',response_model=SourceDTO)
def create_source(body:CameraCreate,request:Request,db=Depends(get_db)):
    address, credentials, _ = camera_address(body.address,values_for(db,'security')['camera_allowed_networks'])
    if body.username is not None:
        credentials['username'] = body.username
    if body.password is not None:
        credentials['password'] = body.password
    source = Source(name=body.name,kind='camera',status='unverified',address=address,credentials=request.app.state.vault.encrypt(credentials))
    db.add(source)
    db.flush()
    notify_source(db,source)
    db.add(Log(level='INFO',module='sources',message='已添加摄像头视频源；尚未验证连接。'))
    return source_dto(source)

@router.get('/sources/{source_id}',response_model=SourceDTO)
def read_source(source_id:str,db=Depends(get_db)):
    return source_dto(get_source(db,source_id))

@router.patch('/sources/{source_id}',response_model=SourceDTO)
def patch_source(source_id:str,body:SourcePatch,request:Request,db=Depends(get_db)):
    source = get_source(db,source_id)
    changes = {'updated_at':now(),'row_version':body.row_version+1}
    if 'name' in body.model_fields_set:
        if body.name is None:
            raise Error(422,'validation_error','名称不能为空。')
        changes['name'] = body.name
    camera_fields = body.model_fields_set & {'address','username','password'}
    if camera_fields:
        if source.kind!='camera':
            raise Error(422,'validation_error','文件视频源不能设置摄像头连接。')
        try:
            creds = request.app.state.vault.decrypt(source.credentials)
        except InvalidToken:
            if {'username','password'} <= body.model_fields_set:
                creds = {'username':'','password':''}
            else:
                raise Error(422,'credentials_unavailable','原凭据无法解密，请同时重新填写用户名和密码。')
        address, inline, _ = camera_address(body.address or source.address,values_for(db,'security')['camera_allowed_networks'])
        if inline['username'] or inline['password']:
            creds.update(inline)
        for key in ('username','password'):
            if key in body.model_fields_set:
                creds[key] = getattr(body,key) or ''
        changes.update(address=address,credentials=request.app.state.vault.encrypt(creds),status='unverified',observed_at=None,error_code=None,error_message=None)
    updated = db.execute(update(Source).where(Source.id==source_id,Source.row_version==body.row_version,Source.archived==False).values(**changes))
    if updated.rowcount!=1:
        raise Error(409,'version_conflict','视频源已修改，请刷新后重试。')
    if camera_fields:
        db.execute(update(Job).where(Job.source_id==source_id,Job.kind=='camera_test',Job.state.in_(['queued','running'])).values(state='canceled',lease_owner=None,lease_until=None))
    db.refresh(source)
    notify_source(db,source)
    return source_dto(source)

@router.post('/sources/{source_id}/archive',status_code=204)
def archive_source(source_id:str,db=Depends(get_db)):
    source = get_source(db,source_id)
    source.archived, source.updated_at = True, now()
    source.row_version += 1
    db.execute(update(Job).where(Job.source_id==source_id,Job.state.in_(['queued','running'])).values(state='canceled',lease_owner=None,lease_until=None))
    db.execute(update(Upload).where(Upload.source_id==source_id,Upload.state.in_(['uploading','probing','transcoding'])).values(state='canceled'))
    db.add(Notification(type='source',aggregate_id=source.id,payload={'id':source.id,'archived':True}))
    db.add(Log(level='INFO',module='sources',message='已归档视频源。'))

@router.post('/sources/{source_id}/tests',response_model=SourceTestDTO)
def start_test(source_id:str,db=Depends(get_db)):
    source = get_source(db,source_id)
    if source.kind!='camera':
        raise Error(422,'camera_required','连接测试仅用于摄像头。')
    existing = db.scalar(select(Job).where(Job.source_id==source.id,Job.kind=='camera_test',Job.state.in_(['queued','running'])))
    if existing:
        return existing
    source.status, source.updated_at = 'connecting', now()
    source.row_version += 1
    source.error_code = source.error_message = None
    job = Job(kind='camera_test',source_id=source.id)
    db.add(job)
    db.flush()
    notify_source(db,source)
    return job

@router.get('/source-tests/{job_id}',response_model=SourceTestDTO)
def get_test(job_id:str,db=Depends(get_db)):
    job = db.get(Job,job_id)
    if not job or job.kind!='camera_test':
        raise Error(404,'test_not_found','测试记录不存在。')
    get_source(db,job.source_id)
    return job

@router.post('/sources/{source_id}/preview-sessions',response_model=PreviewDTO)
def preview_session(source_id:str,request:Request,db=Depends(get_db)):
    source = get_source(db,source_id)
    if source.kind=='camera':
        request.app.state.media_gateway.ensure_published(source,values_for(db,'security')['camera_allowed_networks'])
        return {'session_id':uid(),'protocol':'hls','playback_url':f'/api/v1/sources/{source.id}/live/index.m3u8','expires_at':(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat().replace('+00:00','Z')}
    if source.status!='ready' or not source.media_key:
        raise Error(409,'media_not_ready','视频仍未准备就绪，请检查探测或转码状态。')
    return {'session_id':uid(),'protocol':'file','playback_url':f'/api/v1/sources/{source.id}/media','expires_at':(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat().replace('+00:00','Z')}

@router.get('/sources/{source_id}/live/{asset_path:path}',response_class=Response)
def live_media(source_id:str,asset_path:str,request:Request,db=Depends(get_db)):
    source = get_source(db,source_id)
    if source.kind!='camera':
        raise Error(404,'media_missing','该视频源没有直播资源。')
    prefix = f'/api/v1/sources/{source.id}/live/'
    content,status,media_type,headers = request.app.state.media_gateway.read(
        source,values_for(db,'security')['camera_allowed_networks'],asset_path,prefix,
        query=request.url.query,range_header=request.headers.get('range'))
    return Response(content=content,status_code=status,media_type=media_type,headers=headers)

@router.get('/sources/{source_id}/media')
def media(source_id:str,request:Request,db=Depends(get_db)):
    source = get_source(db,source_id)
    if source.status!='ready' or not source.media_key:
        raise Error(409,'media_not_ready','媒体尚未准备就绪。')
    path = controlled_path(request.app.state.config,'media',source.media_key)
    if not path.is_file():
        raise Error(404,'media_missing','媒体文件不存在，请重新导入。')
    return FileResponse(path,media_type='video/mp4',headers={'Cache-Control':'private, no-store'})

@router.get('/sources/{source_id}/thumbnail')
def thumbnail(source_id:str,request:Request,db=Depends(get_db)):
    source = get_source(db,source_id)
    if not source.thumbnail_key:
        raise Error(404,'thumbnail_unavailable','缩略图未生成。')
    path = controlled_path(request.app.state.config,'media',source.thumbnail_key)
    if not path.is_file():
        raise Error(404,'thumbnail_unavailable','缩略图不存在。')
    return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'private, no-store'})

@router.post('/uploads',response_model=UploadDTO)
def create_upload(body:UploadCreate,request:Request,db=Depends(get_db)):
    if body.size_bytes > values_for(db,'storage')['max_upload_mb']*1024*1024:
        raise Error(413,'upload_too_large','文件超过当前上传大小限制。')
    upload = Upload(filename=body.filename,size_bytes=body.size_bytes)
    db.add(upload)
    db.flush()
    controlled_path(request.app.state.config,'uploads',upload.id).mkdir(exist_ok=True)
    return upload

@router.get('/uploads/{upload_id}',response_model=UploadDTO)
def read_upload(upload_id:str,db=Depends(get_db)):
    return get_upload(db,upload_id)

@router.put('/uploads/{upload_id}/chunks/{number}',response_model=UploadDTO)
async def write_chunk(upload_id:str,number:int,request:Request,db=Depends(get_db)):
    data = bytearray()
    async for part in request.stream():
        data.extend(part)
        if len(data)>request.app.state.config.max_chunk_bytes:
            raise Error(413,'chunk_too_large','单块不得超过 8 MiB。')
    if not data or number<0:
        raise Error(422,'invalid_chunk','分块不能为空，编号从 0 开始。')
    # End any read transaction before taking the SQLite writer lock.
    db.commit()
    db.execute(text('BEGIN IMMEDIATE'))
    upload = get_upload(db,upload_id)
    if upload.state!='uploading':
        raise Error(409,'upload_not_writable','上传已提交或取消。')
    key, sha = str(number), hashlib.sha256(data).hexdigest()
    if key in upload.chunks:
        if upload.chunks[key]['sha256'] != sha or upload.chunks[key]['size']!=len(data):
            raise Error(409,'chunk_conflict','同编号分块的内容不一致。')
        return upload
    if number!=len(upload.chunks):
        raise Error(409,'chunk_out_of_order','请按顺序上传分块。')
    if upload.received_bytes+len(data)>upload.size_bytes:
        raise Error(413,'upload_too_large','分块总大小超过声明的文件大小。')
    folder = controlled_path(request.app.state.config,'uploads',upload.id)
    path = folder / f'{number}.chunk'
    temporary = folder / f'{number}.{uid()}.tmp'
    with temporary.open('wb') as file:
        file.write(data)
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(path)
    upload.chunks = {**upload.chunks,key:{'sha256':sha,'size':len(data)}}
    upload.received_bytes += len(data)
    return upload

@router.post('/uploads/{upload_id}/complete',response_model=UploadDTO)
def complete_upload(upload_id:str,body:UploadComplete,request:Request,db=Depends(get_db)):
    db.commit()
    db.execute(text('BEGIN IMMEDIATE'))
    upload = get_upload(db,upload_id)
    if upload.state=='canceled':
        raise Error(409,'upload_canceled','上传已取消。')
    if upload.source_id:
        return upload
    if upload.received_bytes!=upload.size_bytes:
        raise Error(409,'upload_incomplete','文件尚未上传完整。')
    source = Source(name=body.name or upload.filename[:160],kind='file',status='probing',size_bytes=upload.size_bytes)
    db.add(source)
    db.flush()
    upload.source_id, upload.state = source.id, 'probing'
    db.add(Job(kind='media_probe',source_id=source.id,upload_id=upload.id))
    notify_source(db,source)
    return upload

@router.delete('/uploads/{upload_id}',status_code=204)
def cancel_upload(upload_id:str,db=Depends(get_db)):
    db.commit()
    db.execute(text('BEGIN IMMEDIATE'))
    upload = get_upload(db,upload_id)
    if upload.state=='ready':
        raise Error(409,'upload_completed','导入已完成，请归档视频源。')
    upload.state = 'canceled'
    if upload.source_id:
        source = db.get(Source,upload.source_id)
        if source:
            source.status, source.updated_at = 'canceled', now()
            source.row_version += 1
            notify_source(db,source)
    db.execute(update(Job).where(Job.upload_id==upload_id,Job.state.in_(['queued','running'])).values(state='canceled',lease_owner=None,lease_until=None))
