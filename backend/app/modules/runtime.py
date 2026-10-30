from collections import deque
import shutil
import time
import psutil
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy import select, func
from ..shared.db import get_db
from ..shared.models import Source, Worker, Log, now
from ..schemas import RuntimeDTO, DashboardDTO, EventPage, LogPage
from .sources import source_dto
from .agents.workspace import WORKSPACE_ACTOR_ID
from .agents.contracts import ExecutionSummary
from .models.models import ModelPair
from .models.schemas import ModelInput

router = APIRouter(tags=['runtime'])

def executable(value):
    return shutil.which(value) is not None

def worker_rows(db):
    return list(db.scalars(select(Worker).where(Worker.heartbeat_at>time.time()-15)))

def dependency_services(app,db,local_model=None):
    observed = now()
    worker = bool(worker_rows(db))
    ffmpeg = executable(app.state.config.ffmpeg) and executable(app.state.config.ffprobe)
    gateway = app.state.media_gateway.health()
    if local_model is None:
        local_model = bool(getattr(app.state.model_services,'is_ready',lambda:False)())
    return [
        {'key':'api','name':'API','status':'ready','message':'API 与持久层可用。','observed_at':observed},
        {'key':'worker','name':'Worker','status':'ready' if worker else 'unavailable','message':'独立 Worker 心跳正常。' if worker else '未收到独立 Worker 心跳，请启动 Worker。','observed_at':observed},
        {'key':'ffmpeg','name':'FFmpeg / FFprobe','status':'ready' if ffmpeg else 'unavailable','message':'本地媒体工具可用。' if ffmpeg else '请安装 FFmpeg 与 FFprobe，并设置 VISION_FFMPEG / VISION_FFPROBE。','observed_at':observed},
        {'key':'media_gateway','name':'MediaMTX','status':'ready' if gateway else 'unavailable','message':'本机媒体网关已连接。' if gateway else '本机媒体网关未就绪，请启动摄像头媒体服务。','observed_at':observed},
        {'key':'models','name':'本地模型运行时','status':'ready' if local_model else 'unavailable','message':'YOLO11n CPU ONNX 执行器与可信模型已就绪。' if local_model else '可信本地模型尚未安装或依赖不可用，请先准备 YOLO 模型。','observed_at':observed},
        {'key':'gpu','name':'GPU 采集器','status':'unavailable','message':'未接入 GPU 采集器，使用率未知。','observed_at':observed},
    ]

def execution_summary(app):
    return ExecutionSummary.model_validate(app.state.agent_services.summary(WORKSPACE_ACTOR_ID))


def summary_events(db, summary):
    names = dict(db.execute(select(Source.id, Source.name)).all())
    return [dict(id=e.id, agent_id=e.agent_id, event_type=e.event_type, source_id=e.source_id,
        source_name=names.get(e.source_id), run_id=e.run_id, revision_id=e.revision_id,
        occurred_at=e.occurred_at, start_media_ms=e.start_media_ms, reason=e.reason,
        evidence_status=e.evidence_status, review_status=e.review_status) for e in summary.recent_events]


def runtime_models(app, db, runtime_ready):
    origin = getattr(app.state.model_services, 'data_origin', 'real')
    pairs = db.scalars(select(ModelPair).where(
        ModelPair.status == 'available', ModelPair.data_origin == origin,
    ).order_by(ModelPair.created_at.desc(), ModelPair.model_id, ModelPair.version)).all()
    result = []
    for pair in pairs:
        definition = ModelInput.model_validate(pair.definition)
        if pair.validation == 'passed' and runtime_ready:
            status, message = 'ready', '模型校验通过，当前本地执行器可用。'
        elif pair.validation == 'passed':
            status, message = 'unavailable', '模型已校验，但本地执行器或可信模型产物当前不可用。'
        else:
            status, message = pair.validation, pair.validation_message
        result.append({'id':pair.model_id, 'name':definition.name, 'version':pair.version,
            'runtime_type':definition.runtime_type, 'template_name':definition.template.name,
            'status':status, 'message':message, 'data_origin':pair.data_origin})
    return result


def runtime_snapshot(app,db,record=True):
    summary = execution_summary(app)
    local_model_ready = bool(getattr(app.state.model_services,'is_ready',lambda:False)())
    sample = {'observed_at':now(),'cpu_percent':psutil.cpu_percent(interval=0.1),'memory_percent':psutil.virtual_memory().percent,'gpu_percent':None}
    if record:
        app.state.runtime_history.append(sample)
    usage = shutil.disk_usage(app.state.config.var_root)
    total = db.scalar(select(func.count()).select_from(Source).where(Source.archived==False))
    online = db.scalar(select(func.count()).select_from(Source).where(Source.archived==False,Source.kind=='camera',Source.status=='online'))
    return {**sample,'disk':{'used_bytes':usage.used,'total_bytes':usage.total,'free_bytes':usage.free},'sources':{'total':total,'online':online},'runs':{'running':summary.active_runs,'completed':summary.completed,'failed':summary.failed},'data_origin':summary.data_origin,'runtime_available':summary.active_runs is not None,'services':dependency_services(app,db,local_model_ready),'models':runtime_models(app,db,local_model_ready),'workers':[{'id':w.id,'status':'online','observed_at':__import__('datetime').datetime.fromtimestamp(w.heartbeat_at,__import__('datetime').timezone.utc).isoformat().replace('+00:00','Z')} for w in worker_rows(db)],'history':list(app.state.runtime_history)}

@router.get('/runtime/overview',response_model=RuntimeDTO)
def overview(request:Request,db=Depends(get_db)):
    return runtime_snapshot(request.app,db)

@router.get('/dashboard',response_model=DashboardDTO)
def dashboard(request:Request,db=Depends(get_db)):
    summary = execution_summary(request.app)
    sources = list(db.scalars(select(Source).where(Source.archived==False).order_by(Source.created_at.desc()).limit(100)))
    total = db.scalar(select(func.count()).select_from(Source).where(Source.archived==False))
    online = db.scalar(select(func.count()).select_from(Source).where(Source.archived==False,Source.kind=='camera',Source.status=='online'))
    return {'counts':{'sources_total':total,'sources_online':online,'active_runs':summary.active_runs,'today_events':summary.today_events},'sources':[source_dto(s) for s in sources],'recent_events':summary_events(db,summary)[:5],'task_summary':{'running':summary.running,'completed':summary.completed,'waiting':summary.waiting},'data_origin':summary.data_origin,'runtime_available':summary.active_runs is not None,'events_available':summary.today_events is not None}

@router.get('/events',response_model=EventPage)
def events(request:Request,db=Depends(get_db)):
    summary = execution_summary(request.app)
    return {'items':summary_events(db,summary),'next_cursor':None,'data_origin':summary.data_origin,'available':summary.today_events is not None}

@router.get('/runs')
def runs():
    return {'items':[],'next_cursor':None}

@router.get('/logs',response_model=LogPage)
def logs(level:str|None=None,q:str='',limit:int=Query(100,ge=1,le=500),db=Depends(get_db)):
    statement = select(Log)
    if level:
        statement = statement.where(Log.level==level.upper())
    if q:
        statement = statement.where(Log.message.contains(q,autoescape=True))
    return {'items':list(db.scalars(statement.order_by(Log.occurred_at.desc()).limit(limit))),'next_cursor':None}

@router.get('/health/live')
def live():
    return {'status':'ok'}

@router.get('/health/ready')
def ready(request:Request,db=Depends(get_db)):
    return {'status':'ready','services':dependency_services(request.app,db)}
