from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from sqlalchemy import update
from ..schemas import General, Storage, Resources, Security, SettingsPatch, SettingsDTO
from ..shared.models import Setting, Log
from ..shared.db import get_db
from ..shared.errors import Error

router = APIRouter(prefix='/settings',tags=['settings'])
SECTIONS = {'general':General,'storage':Storage,'resources':Resources,'security':Security}

def initialize(db):
    for section, schema in SECTIONS.items():
        record = db.get(Setting,section)
        if not record:
            db.add(Setting(section=section,values=schema().model_dump()))
        elif section == 'security' and 'session_timeout_minutes' in record.values:
            record.values = {key:value for key,value in record.values.items() if key != 'session_timeout_minutes'}
            record.row_version += 1
    db.commit()

def values_for(db, section):
    record = db.get(Setting,section)
    return record.values if record else SECTIONS[section]().model_dump()

@router.get('/{section}',response_model=SettingsDTO)
def get_settings(section:str, request:Request,  db=Depends(get_db)):
    if section == 'diagnostics':
        from .runtime import dependency_services
        services = dependency_services(request.app,db)
        statuses = {v['key']:v['status'] for v in services}
        return {'section':section,'values':{'version':request.app.state.config.version,'media_gateway_configured':statuses['media_gateway']=='ready','ffmpeg_available':statuses['ffmpeg']=='ready','worker_online':statuses['worker']=='ready','configuration_sources':{'storage':'VISION_VAR_ROOT environment or local default','ffmpeg':'VISION_FFMPEG / VISION_FFPROBE environment or PATH','media_gateway':'VISION_MEDIA_GATEWAY_API_URL / VISION_MEDIA_GATEWAY_HLS_URL environment or loopback default'}},'row_version':1}
    record = db.get(Setting,section)
    if not record:
        raise Error(404,'section_not_found','设置分类不存在。')
    return record

@router.patch('/{section}',response_model=SettingsDTO)
def patch_settings(section:str,body:SettingsPatch,db=Depends(get_db)):
    if section == 'diagnostics':
        raise Error(403,'read_only','诊断配置为只读。')
    if section not in SECTIONS:
        raise Error(404,'section_not_found','设置分类不存在。')
    record = db.get(Setting,section)
    try:
        values = SECTIONS[section].model_validate({**record.values,**body.values}).model_dump()
    except ValidationError as exc:
        raise Error(422,'validation_error','设置字段或值不符合要求。',[{'field':'.'.join(map(str,e['loc'])),'type':e['type']} for e in exc.errors()])
    updated = db.execute(update(Setting).where(Setting.section==section,Setting.row_version==body.row_version).values(values=values,row_version=body.row_version+1))
    if updated.rowcount != 1:
        raise Error(409,'version_conflict','设置已被其他操作修改，请刷新后重试。')
    db.add(Log(level='INFO',module='settings',message=f'已保存 {section} 设置。'))
    return {'section':section,'values':values,'row_version':body.row_version+1}
