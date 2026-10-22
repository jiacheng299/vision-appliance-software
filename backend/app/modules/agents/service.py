"""Own only agent/revision tables; external capabilities stay behind public queries."""
import base64
import hashlib
import json
from sqlalchemy import and_, or_, select, text
from ...shared.errors import Error
from ...shared.models import Log, now
from ..sources import resolve_agent_source
from .models import Agent, AgentCommand, AgentRevision
from .schemas import AgentDTO, AgentDetail, RevisionConfig, RevisionDTO, channel_sources


def lock_write(db):
    # Serialize short definition changes and idempotency receipts, never model calls.
    db.execute(text('BEGIN IMMEDIATE'))


def get_agent(db, agent_id):
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise Error(404, 'agent_not_found', '智能体不存在，请刷新列表。')
    return agent


def get_revision(db, revision_id):
    revision = db.get(AgentRevision, revision_id)
    if revision is None:
        raise Error(404, 'revision_not_found', '配置版本不存在。')
    return revision


def revisions_for(db, agent_id):
    return list(db.scalars(select(AgentRevision).where(AgentRevision.agent_id == agent_id).order_by(AgentRevision.revision_no.desc())))


def agent_dto(db, agent, detail=False):
    revisions = revisions_for(db, agent.id)
    data = dict(id=agent.id, name=agent.name, description=agent.description, row_version=agent.row_version,
                created_at=agent.created_at, updated_at=agent.updated_at, archived_at=agent.archived_at,
                desired_revision_id=agent.desired_revision_id, latest_revision=RevisionDTO.model_validate(revisions[0]))
    if detail:
        return AgentDetail(**data, revisions=[RevisionDTO.model_validate(r) for r in revisions])
    return AgentDTO(**data)


def list_agents(db, q, source_id, cursor, limit, archived=False, provider=None, actor_id=None, status=None, scene=None, sort='updated_desc'):
    statement = select(Agent).where(Agent.archived_at.is_not(None) if archived else Agent.archived_at.is_(None))
    if q:
        statement = statement.where(or_(Agent.name.contains(q, autoescape=True), Agent.description.contains(q, autoescape=True)))
    if cursor:
        try:
            updated_at, identifier = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
            if not isinstance(updated_at, str) or not isinstance(identifier, str):
                raise ValueError()
        except (ValueError, TypeError, UnicodeError):
            raise Error(422, 'invalid_cursor', '分页位置无效，请刷新列表。')
        statement = statement.where(or_(Agent.name > updated_at, and_(Agent.name == updated_at, Agent.id > identifier))) if sort == 'name_asc' else statement.where(or_(Agent.updated_at < updated_at, and_(Agent.updated_at == updated_at, Agent.id < identifier)))
    result = []
    # Filter only latest revisions; a source used by an older snapshot must not match.
    ordering = (Agent.name.asc(), Agent.id.asc()) if sort == 'name_asc' else (Agent.updated_at.desc(), Agent.id.desc())
    for agent in db.scalars(statement.order_by(*ordering)):
        dto = agent_dto(db, agent)
        if source_id and not any(b.source_id == source_id for c in dto.latest_revision.config.channels for b in channel_sources(c)):
            continue
        if scene and not any(c.rule == scene for c in dto.latest_revision.config.channels):
            continue
        if provider:
            from .workflow import enrich
            dto = enrich(db, dto, provider, actor_id)
        if status and dto.status != status:
            continue
        result.append(dto)
        if len(result) == limit+1:
            break
    next_cursor = None
    if len(result) > limit:
        last = result[limit-1]
        next_cursor = base64.urlsafe_b64encode(json.dumps([last.name if sort == 'name_asc' else last.updated_at, last.id]).encode()).decode()
    return {'items': result[:limit], 'next_cursor': next_cursor}


def check_config(db, config: RevisionConfig, previous: dict | None = None):
    old = RevisionConfig.model_validate(previous).channels if previous else []
    old_sources = {(c.channel_id, b.source_id) for c in old for b in channel_sources(c)}
    for channel in config.channels:
        for binding in channel_sources(channel):
            source = resolve_agent_source(db, binding.source_id, allow_archived=(channel.channel_id, binding.source_id) in old_sources)
            if binding.start_media_ms is not None:
                if source.kind != 'file' or source.duration_ms is None or binding.end_media_ms > source.duration_ms:
                    raise Error(422, 'invalid_media_range', '录像区间超出视频时长，或该视频源不支持区间。')


def receipt(db, actor_id, key, operation, payload):
    request_hash = hashlib.sha256(json.dumps([operation, payload], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    existing = db.scalar(select(AgentCommand).where(AgentCommand.actor_id == actor_id, AgentCommand.command_key == key))
    if existing and existing.request_hash != request_hash:
        raise Error(409, 'idempotency_conflict', '同一请求编号已用于不同内容，请重新发起操作。')
    return existing, request_hash


def create_agent(db, body, actor_id, key):
    lock_write(db)
    existing, request_hash = receipt(db, actor_id, key, 'create', body.model_dump(mode='json', exclude_unset=True))
    if existing:
        return AgentDetail.model_validate(existing.response)
    check_config(db, body.config)
    agent = Agent(name=body.name, description=body.description, owner_id=actor_id)
    db.add(agent)
    db.flush()
    db.add(AgentRevision(agent_id=agent.id, revision_no=1, config=body.config.model_dump(mode='json')))
    db.flush()
    result = agent_dto(db, agent, detail=True)
    db.add(AgentCommand(actor_id=actor_id, command_key=key, request_hash=request_hash, response=result.model_dump(mode='json')))
    db.add(Log(level='INFO', module='agents', message=f'创建智能体草稿 {agent.id}。'))
    return result


def check_version(resource, expected):
    if resource.row_version != expected:
        raise Error(409, 'revision_conflict', '配置已被其他页面更新，请先保留当前输入，再刷新并比较。')


def patch_agent(db, agent_id, body):
    lock_write(db)
    agent = get_agent(db, agent_id)
    from .workflow import writable
    writable(agent)
    check_version(agent, body.row_version)
    agent.name, agent.description = body.name, body.description
    agent.row_version += 1
    agent.updated_at = now()
    db.flush()
    return agent_dto(db, agent, detail=True)


def clone_revision(db, agent_id, body, actor_id, key, baseline_run_id=None, baseline_channel_id=None, baseline_source_id=None):
    lock_write(db)
    existing, request_hash = receipt(db, actor_id, key, f'clone:{agent_id}', {**body.model_dump(mode='json'), 'baseline_run_id': baseline_run_id, 'baseline_channel_id': baseline_channel_id, 'baseline_source_id': baseline_source_id})
    if existing:
        return RevisionDTO.model_validate(existing.response)
    agent = get_agent(db, agent_id)
    from .workflow import writable
    writable(agent)
    check_version(agent, body.row_version)
    base = get_revision(db, body.base_revision_id)
    if base.agent_id != agent_id:
        raise Error(422, 'revision_agent_mismatch', '不能复制其他智能体的配置版本。')
    config = base.config if baseline_channel_id is None else {**base.config, 'channels': [c for c in base.config['channels'] if c['channel_id'] == baseline_channel_id]}
    if baseline_source_id:
        config = RevisionConfig.model_validate(config).model_copy(deep=True)
        for c in config.channels:
            binding = next(b for b in channel_sources(c) if b.source_id == baseline_source_id)
            if c.sources:
                c.sources = [binding]
        config = config.model_dump(mode='json')
    revision = AgentRevision(agent_id=agent_id, revision_no=revisions_for(db, agent_id)[0].revision_no+1, base_revision_id=base.id, config=config, baseline_run_id=baseline_run_id or base.baseline_run_id)
    db.add(revision)
    agent.updated_at = now()
    agent.row_version += 1
    db.flush()
    result = RevisionDTO.model_validate(revision)
    db.add(AgentCommand(actor_id=actor_id, command_key=key, request_hash=request_hash, response=result.model_dump(mode='json')))
    return result


def patch_revision(db, revision_id, body):
    lock_write(db)
    revision = get_revision(db, revision_id)
    from .workflow import writable
    writable(get_agent(db, revision.agent_id))
    check_version(revision, body.row_version)
    if revision.state != 'draft':
        raise Error(409, 'revision_immutable', '已发布版本不能修改，请复制为新草稿。')
    check_config(db, body.config, revision.config)
    revision.config = body.config.model_dump(mode='json')
    revision.latest_validation_id = None
    revision.row_version += 1
    revision.updated_at = now()
    agent = get_agent(db, revision.agent_id)
    agent.updated_at = revision.updated_at
    agent.row_version += 1
    db.flush()
    return RevisionDTO.model_validate(revision)
