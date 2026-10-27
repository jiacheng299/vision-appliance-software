from sqlalchemy import select
from ...shared.errors import Error
from ...shared.models import now, uid, Log
from ...shared.monitoring_parameters import CORE_KEYS, ParameterSetting, validate_settings
from ..agents import service as tasks, workflow
from ..agents.models import Agent, AgentCommand, AgentRevision
from ..agents.schemas import AgentCreate, AgentDetail, AgentTemplateRef, ChannelConfig, RevisionConfig, channel_sources
from ..agents.workspace import WORKSPACE_ACTOR_ID
from ..sources import resolve_agent_source
from .models import AgentTemplate, AgentTemplateRevision, TemplateTaskLink
from .schemas import *

def get_template(db,identifier):
    row=db.get(AgentTemplate,identifier)
    if not row: raise Error(404,'template_not_found','智能体模板不存在。')
    return row

def revisions(db,identifier):
    return list(db.scalars(select(AgentTemplateRevision).where(AgentTemplateRevision.template_id==identifier).order_by(AgentTemplateRevision.revision_no.desc())))

def source_rows(db,agent_id):
    found={}
    for revision in tasks.revisions_for(db,agent_id):
        for channel in revision.config.get('channels',[]):
            for binding in channel_sources(channel):
                if binding.source_id in found: continue
                try:
                    try:
                        source=resolve_agent_source(db,binding.source_id);status=source.status
                    except Error:
                        source=resolve_agent_source(db,binding.source_id,allow_archived=True);status='archived'
                    found[source.id]=TemplateSource(id=source.id,name=source.name,kind=source.kind,status=status)
                except Error:
                    found[binding.source_id]=TemplateSource(id=binding.source_id,name=binding.source_id,kind='unknown',status='unavailable')
    return list(found.values())

def dto(db,row,detail=False):
    versions=revisions(db,row.id)
    links=list(db.scalars(select(TemplateTaskLink).where(TemplateTaskLink.template_id==row.id)))
    source_ids={s.id for link in links for s in source_rows(db,link.agent_id)}
    published=next((r for r in versions if r.state=='published'),None)
    data=dict(id=row.id,name=row.name,description=row.description,row_version=row.row_version,
        created_at=row.created_at,updated_at=row.updated_at,archived_at=row.archived_at,imported_from_agent_id=row.imported_from_agent_id,
        latest_revision=TemplateRevisionDTO.model_validate(versions[0]),published_revision=TemplateRevisionDTO.model_validate(published) if published else None,
        task_count=len(links),source_count=len(source_ids))
    return TemplateDetail(**data,revisions=[TemplateRevisionDTO.model_validate(v) for v in versions]) if detail else TemplateDTO(**data)

def list_templates(db,q='',cursor=None,limit=24,published_only=False,archived=False):
    query=select(AgentTemplate).where(AgentTemplate.archived_at.is_not(None) if archived else AgentTemplate.archived_at.is_(None)).order_by(AgentTemplate.id)
    if q: query=query.where(AgentTemplate.name.contains(q,autoescape=True))
    if cursor: query=query.where(AgentTemplate.id>cursor)
    output=[]
    for row in db.scalars(query):
        item=dto(db,row)
        if published_only and not item.published_revision: continue
        output.append(item)
        if len(output)>limit: break
    return TemplatePage(items=output[:limit],next_cursor=output[limit-1].id if len(output)>limit else None)

def writable(row):
    if row.archived_at: raise Error(409,'template_archived','模板已归档，不能修改或用于新建任务。')

def check_settings(config,item=None,complete=False):
    extra={'target':item.targets,'rule':item.rules} if item else {}
    return validate_settings(config.parameters,complete=complete,extra_choices=extra)

def model_choice(provider,reference):
    if provider is None or reference is None: return None
    try: return next((i for i in provider.catalog(WORKSPACE_ACTOR_ID).items if i.reference==reference),None)
    except Error as exc:
        if exc.status!=503: raise
        return None

def create_template(db,body,actor,key,provider=None):
    check_settings(body.config,model_choice(provider,body.config.model_ref))
    tasks.lock_write(db)
    existing,signature=tasks.receipt(db,actor,key,'agent-template-create',body.model_dump(mode='json'))
    if existing: return TemplateDetail.model_validate(existing.response)
    row=AgentTemplate(name=body.name,description=body.description)
    db.add(row);db.flush()
    db.add(AgentTemplateRevision(template_id=row.id,revision_no=1,config=body.config.model_dump(mode='json')));db.flush()
    result=dto(db,row,True)
    db.add(AgentCommand(actor_id=actor,command_key=key,request_hash=signature,response=result.model_dump(mode='json')))
    return result

def patch_template(db,identifier,body,provider=None):
    check_settings(body.config,model_choice(provider,body.config.model_ref))
    tasks.lock_write(db);row=get_template(db,identifier);writable(row);tasks.check_version(row,body.row_version)
    latest=revisions(db,identifier)[0]
    if latest.state=='published':
        latest=AgentTemplateRevision(template_id=identifier,revision_no=latest.revision_no+1,config=body.config.model_dump(mode='json'))
        db.add(latest)
    else: latest.config=body.config.model_dump(mode='json')
    row.name,row.description=body.name,body.description
    row.updated_at=now();row.row_version+=1;db.flush()
    return dto(db,row,True)

def publish_template(db,identifier,body,provider,actor,key):
    existing,_=tasks.receipt(db,actor,key,f'agent-template-publish:{identifier}',body.model_dump(mode='json'))
    if existing: return TemplateDetail.model_validate(existing.response)
    # Catalog access precedes the short SQLite write lock.
    catalog=provider.catalog(actor)
    db.rollback();tasks.lock_write(db)
    existing,signature=tasks.receipt(db,actor,key,f'agent-template-publish:{identifier}',body.model_dump(mode='json'))
    if existing: return TemplateDetail.model_validate(existing.response)
    row=get_template(db,identifier);writable(row);tasks.check_version(row,body.row_version)
    version=db.get(AgentTemplateRevision,body.revision_id)
    if not version or version.template_id!=identifier: raise Error(422,'template_revision_mismatch','模板版本不属于当前模板。')
    if version.state!='draft' or version.id!=revisions(db,identifier)[0].id: raise Error(409,'template_immutable','该模板版本不能修改或重复发布。')
    config=TemplateConfig.model_validate(version.config)
    item=next((v for v in catalog.items if v.reference==config.model_ref),None)
    if not item: raise Error(422,'template_model_unavailable','请选择当前可用且经过校验的模型。')
    values=check_settings(config,item)
    target=values.get('target') or (item.targets[0] if len(item.targets)==1 else '')
    rule=values.get('rule') or (item.rules[0] if len(item.rules)==1 else '')
    if target not in item.targets or rule not in item.rules:
        raise Error(422,'template_conditions_required','模型支持多种对象或规则，请从配置项中明确选择检测对象和触发规则。')
    config.default_target,config.default_rule=target,rule
    config.title,config.summary=row.name,row.description
    version.config=config.model_dump(mode='json');version.state='published';version.published_at=now()
    row.updated_at=version.published_at;row.row_version+=1;db.flush()
    result=dto(db,row,True)
    db.add(AgentCommand(actor_id=actor,command_key=key,request_hash=signature,response=result.model_dump(mode='json')))
    return result

def selected_settings(config,overrides):
    chosen={p.key:p.model_copy(deep=True) for p in config.parameters}
    if len({p.key for p in overrides})!=len(overrides): raise Error(422,'invalid_parameters','任务配置项重复。')
    for setting in overrides:
        if setting.key not in chosen: raise Error(422,'template_parameter_mismatch','任务只能填写该模板已选择的配置项。')
        chosen[setting.key].value=setting.value
    result=list(chosen.values())
    validate_settings(result,complete=True,extra_choices={'target':[config.default_target],'rule':[config.default_rule]})
    return result

def effective_conditions(config,settings):
    values={p.key:p.value for p in settings if p.value is not None and p.value!=''}
    return str(values.get('target',config.default_target)),str(values.get('rule',config.default_rule)),values.get('duration_seconds')

def instantiate(db,identifier,body,actor,key):
    row=get_template(db,identifier)
    version=db.get(AgentTemplateRevision,body.template_revision_id)
    if not version or version.template_id!=identifier or version.state!='published':
        raise Error(422,'template_not_published','请选择该模板的已发布版本。')
    config=TemplateConfig.model_validate(version.config)
    settings=selected_settings(config,body.parameters)
    target,rule,duration=effective_conditions(config,settings)
    from ..models.planning import NAMES
    canonical=NAMES.get((target,rule),'')
    # Nonstandard rules use the unchanged compatibility assessment path.
    channel=ChannelConfig(channel_id=uid(),name=config.title,task_mode='template' if canonical else None,
        requirement_text=canonical or config.summary or config.title,target=target,rule=rule,duration_seconds=duration,
        capability_ref=config.model_ref,sources=[body.source],parameters=settings)
    reference=AgentTemplateRef(template_id=identifier,revision_id=version.id,revision_no=version.revision_no,name=config.title)
    payload=AgentCreate(name=body.name,description=body.description,config=RevisionConfig(channels=[channel],agent_template_ref=reference))
    # Use a stable channel identity for retries of the same version/source command.
    from uuid import uuid5,NAMESPACE_URL
    payload.config.channels[0].channel_id=str(uuid5(NAMESPACE_URL,f'{actor}:{identifier}:{key}'))
    db.rollback()
    result=tasks.create_agent(db,payload,actor,key,allow_template=True)
    if not db.get(TemplateTaskLink,result.id):
        # Recheck archive/version while holding the creation write lock.
        writable(get_template(db,identifier))
        db.add(TemplateTaskLink(agent_id=result.id,template_id=identifier,template_revision_id=version.id))
    return result

def assert_task_binding(db,agent_id,config):
    link=db.get(TemplateTaskLink,agent_id)
    previous=tasks.revisions_for(db,agent_id)[0].config
    if not link:
        if config.agent_template_ref: raise Error(422,'template_reference_invalid','不能向独立任务添加伪造的模板关联。')
        return
    # Imported legacy tasks retain their original configuration without a synthetic reference.
    if not previous.get('agent_template_ref') and config.agent_template_ref is None: return
    ref=config.agent_template_ref
    if not ref or ref.model_dump()!=previous.get('agent_template_ref'):
        raise Error(422,'template_reference_invalid','旧任务必须保留创建时的模板版本。')
    version=db.get(AgentTemplateRevision,link.template_revision_id)
    if ref.template_id!=link.template_id or ref.revision_id!=version.id: raise Error(422,'template_reference_invalid','模板关联不一致。')
    template=TemplateConfig.model_validate(version.config)
    if len(config.channels)!=1: raise Error(422,'template_task_scope_invalid','模板任务仅允许一路视频配置。')
    channel=config.channels[0]
    if channel.task_mode!=previous['channels'][0].get('task_mode') or channel.execution_plan is not None:
        raise Error(422,'template_execution_immutable','模板任务不能切换执行模式或覆盖模型执行方案。')
    if channel.capability_ref!=template.model_ref or len(channel_sources(channel))!=1:
        raise Error(422,'template_model_immutable','任务必须使用创建时模板的模型及单视频结构。')
    if {p.key for p in channel.parameters}!={p.key for p in template.parameters}:
        raise Error(422,'template_parameter_mismatch','任务不能添加或删除模板配置项。')
    if {p.key:p.required for p in channel.parameters}!={p.key:p.required for p in template.parameters}:
        raise Error(422,'template_parameter_mismatch','任务不能修改模板配置项的必填约束。')
    checked=selected_settings(template,channel.parameters)
    if effective_conditions(template,checked)!=(channel.target,channel.rule,channel.duration_seconds):
        raise Error(422,'template_parameter_mismatch','任务执行条件与模板参数值不一致。')
    from ..models.planning import NAMES
    if channel.task_mode=='template' and (channel.target,channel.rule) in NAMES:
        channel.requirement_text=NAMES[(channel.target,channel.rule)]

def list_tasks(db,identifier,provider,cursor=None,limit=50):
    get_template(db,identifier)
    query=select(TemplateTaskLink).where(TemplateTaskLink.template_id==identifier).order_by(TemplateTaskLink.agent_id)
    if cursor: query=query.where(TemplateTaskLink.agent_id>cursor)
    links=list(db.scalars(query.limit(limit+1)))
    items=[]
    for link in links[:limit]:
        agent=tasks.get_agent(db,link.agent_id)
        item=workflow.enrich(db,tasks.agent_dto(db,agent),provider,WORKSPACE_ACTOR_ID)
        version=db.get(AgentTemplateRevision,link.template_revision_id)
        items.append(TemplateTaskDTO(agent=item,template_revision_id=version.id,template_revision_no=version.revision_no,sources=source_rows(db,agent.id)))
    return TemplateTaskPage(items=items,next_cursor=links[limit-1].agent_id if len(links)>limit else None)
