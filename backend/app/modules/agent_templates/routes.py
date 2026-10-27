from fastapi import APIRouter, Depends, Header, Query
from ...shared.db import get_db
from ...shared.models import now
from ...shared.monitoring_parameters import ParameterCatalog, DEFINITIONS
from ..agents.gateway_routes import providers
from ..agents.workspace import WORKSPACE_ACTOR_ID
from ..agents import service as tasks
from . import service
from .schemas import *

router=APIRouter(tags=['agent-templates'])

@router.get('/agent-parameter-options',response_model=ParameterCatalog)
def parameters():
    return ParameterCatalog(items=DEFINITIONS)

@router.get('/agent-templates',response_model=TemplatePage)
def templates(q:str=Query('',max_length=160),cursor:str|None=Query(None,max_length=80),limit:int=Query(24,ge=1,le=100),published_only:bool=False,archived:bool=False,db=Depends(get_db)):
    return service.list_templates(db,q,cursor,limit,published_only,archived)

@router.post('/agent-templates',response_model=TemplateDetail,status_code=201)
def create(body:TemplateCreate,idempotency_key:str=Header(min_length=1,max_length=128),db=Depends(get_db),provider=Depends(providers)):
    return service.create_template(db,body,WORKSPACE_ACTOR_ID,idempotency_key,provider)

@router.get('/agent-templates/{template_id}',response_model=TemplateDetail)
def detail(template_id:str,db=Depends(get_db)):
    return service.dto(db,service.get_template(db,template_id),True)

@router.patch('/agent-templates/{template_id}',response_model=TemplateDetail)
def patch(template_id:str,body:TemplatePatch,db=Depends(get_db),provider=Depends(providers)):
    return service.patch_template(db,template_id,body,provider)

@router.post('/agent-templates/{template_id}/publish',response_model=TemplateDetail)
def publish(template_id:str,body:TemplateVersionCommand,idempotency_key:str=Header(min_length=1,max_length=128),db=Depends(get_db),provider=Depends(providers)):
    return service.publish_template(db,template_id,body,provider,WORKSPACE_ACTOR_ID,idempotency_key)

@router.post('/agent-templates/{template_id}/archive',response_model=TemplateDetail)
def archive(template_id:str,body:TemplateArchive,db=Depends(get_db)):
    tasks.lock_write(db);row=service.get_template(db,template_id);tasks.check_version(row,body.row_version)
    row.archived_at=now() if body.archived else None;row.updated_at=now();row.row_version+=1;db.flush()
    return service.dto(db,row,True)

@router.get('/agent-templates/{template_id}/tasks',response_model=TemplateTaskPage)
def instances(template_id:str,cursor:str|None=Query(None,max_length=80),limit:int=Query(50,ge=1,le=100),db=Depends(get_db),provider=Depends(providers)):
    return service.list_tasks(db,template_id,provider,cursor,limit)

@router.post('/agent-templates/{template_id}/tasks',response_model=AgentDetail,status_code=201)
def instantiate(template_id:str,body:TemplateTaskCreate,idempotency_key:str=Header(min_length=1,max_length=128),db=Depends(get_db)):
    return service.instantiate(db,template_id,body,WORKSPACE_ACTOR_ID,idempotency_key)

@router.get('/agent-templates/{template_id}/sources',response_model=TemplateSourcePage)
def associated_sources(template_id:str,cursor:str|None=Query(None,max_length=80),limit:int=Query(100,ge=1,le=100),db=Depends(get_db)):
    from sqlalchemy import select
    from .models import TemplateTaskLink
    service.get_template(db,template_id)
    sources={s.id:s for link in db.scalars(select(TemplateTaskLink).where(TemplateTaskLink.template_id==template_id)) for s in service.source_rows(db,link.agent_id)}
    rows=[sources[key] for key in sorted(sources) if cursor is None or key>cursor]
    return TemplateSourcePage(items=rows[:limit],next_cursor=rows[limit-1].id if len(rows)>limit else None)
