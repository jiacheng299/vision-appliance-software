from fastapi import APIRouter, Depends, Header, Query, Request
from ...shared.db import get_db
from ...shared.models import now
from ...shared.monitoring_parameters import ParameterCatalog, DEFINITIONS
from ..agents.gateway_routes import providers
from ..agents.workspace import WORKSPACE_ACTOR_ID
from ..agents import service as tasks
from . import service
from .schemas import *
from .matching import TemplateMatcher, ensure_candidate_current, matcher_values, published_candidates
from .matching_schemas import TemplateMatchRequest, TemplateMatchResult, TemplateMatcherStatus

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

@router.get('/agent-template-matcher',response_model=TemplateMatcherStatus)
def matcher_status(request:Request,db=Depends(get_db)):
    return TemplateMatcher(matcher_values(db,request.app.state.config)).status()

@router.post('/agent-templates/match',response_model=TemplateMatchResult)
def match_template(body:TemplateMatchRequest,request:Request,db=Depends(get_db)):
    values=matcher_values(db,request.app.state.config)
    matcher=TemplateMatcher(values)
    # Missing configuration is explicit even when there are no candidates.
    if not matcher.status().configured:
        return matcher.match(body.requirement_text,[])
    result=matcher.match(body.requirement_text,published_candidates(db))
    ensure_candidate_current(db,result)
    import hashlib, json as jsonlib
    from ...shared.models import Log
    if values.get('_legacy'):
        db.add(Log(level='INFO',module='settings',
                   message='模板匹配使用 VISION_DEEPSEEK_* 旧环境变量配置；请在系统设置的大模型接口中配置，后续版本将移除该回退。'))
    db.add(Log(level='INFO',module='template_matcher',message=jsonlib.dumps({
        'requirement_sha256':hashlib.sha256(body.requirement_text.encode('utf-8')).hexdigest()[:16],
        'status':result.status,'template_id':result.template_id,
        'template_revision_id':result.template_revision_id,'confidence':result.confidence,
        'provider':result.provider,'model':result.model},ensure_ascii=False)))
    return result

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
