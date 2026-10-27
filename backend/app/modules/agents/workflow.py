"""B's immutable configuration workflow. External control stays behind ports."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from sqlalchemy import select
from ...shared.errors import Error
from ...shared.models import Log, now
from ..sources import resolve_agent_source
from .models import AgentCommand, AgentConfirmation, AgentValidation
from .schemas import RevisionDTO, RevisionClone, channel_sources
from .contracts import (ACTIVE_STATES, Assessment, OperationDTO, RuntimeCommand, ValidationDTO, WorkspaceDTO)
from . import service


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def writable(agent):
    if agent.archived_at:
        raise Error(409, 'agent_archived', '智能体已归档，请先恢复后再操作。')


def check_group_support(provider, config):
    if any(c.task_mode == 'natural_language' or c.execution_plan for c in config.channels) and not provider.supports_task_plans:
        raise Error(503, 'task_planning_unavailable', '公共服务尚未支持模板优先的自然语言执行方案。')
    if any(c.execution_plan and c.execution_plan.executor_kind == 'multimodal' for c in config.channels) and not provider.supports_multimodal_tasks:
        raise Error(503, 'multimodal_execution_unavailable', '运行提供方尚未声明支持多模态任务执行。')
    if any(c.sources for c in config.channels) and not provider.supports_grouped_sources:
        raise Error(503, 'grouped_sources_unavailable', '公共服务尚未声明支持通道内多视频源，配置已保留，暂不能验证或启动。')


def source_snapshots(db, config):
    result = []
    for channel in config.channels:
        for binding in channel_sources(channel):
            s = resolve_agent_source(db, binding.source_id)
            result.append({key: getattr(s, key) for key in ('id', 'row_version', 'kind', 'sha256', 'width', 'height', 'duration_ms')})
    return result


def validation_dto(value):
    return ValidationDTO(**value.result, id=value.id, revision_id=value.revision_id, config_hash=value.config_hash, created_at=value.created_at, expires_at=value.expires_at)


def get_validation(db, validation_id):
    value = db.get(AgentValidation, validation_id)
    if not value:
        raise Error(404, 'validation_not_found', '验证记录不存在。')
    return value


def validate(db, revision_id, expected_version, provider, actor_id):
    revision = service.get_revision(db, revision_id)
    writable(service.get_agent(db, revision.agent_id))
    service.check_version(revision, expected_version)
    if revision.state != 'draft':
        raise Error(409, 'revision_immutable', '已发布配置不能再次验证或改写，请复制为新草稿。')
    config = RevisionDTO.model_validate(revision).config
    check_group_support(provider, config)
    config_hash = digest(config.model_dump(mode='json'))
    sources = source_snapshots(db, config)
    sources_hash = digest(sources)
    # Do not hold a SQLite write transaction while an external model responds.
    db.rollback()
    assessment = Assessment.model_validate(provider.assess(config, sources, actor_id))
    if assessment.data_origin != provider.data_origin:
        raise Error(502, 'provider_contract_invalid', '能力服务返回的数据来源标记不一致。')
    missing = []
    if not config.channels:
        missing.append('至少添加一路监测。')
    for c in config.channels:
        if not channel_sources(c):
            missing.append(f'{c.name}：请选择视频源。')
        if not c.requirement_text and c.task_mode != 'template':
            missing.append(f'{c.name}：请填写原始监测需求。')
    if missing:
        assessment.missing_conditions = missing + assessment.missing_conditions
        assessment.verdict = 'clarification_required'
    if assessment.verdict == 'executable' and (assessment.missing_conditions or assessment.unsupported_conditions):
        raise Error(502, 'provider_contract_invalid', '能力服务同时返回可执行和未满足条件，不能发布。')
    if assessment.verdict == 'executable':
        requested = [c.capability_ref.model_dump() for c in config.channels if c.capability_ref]
        chosen = [c.model_dump() for c in assessment.chosen_capabilities]
        multimodal = [c for c in config.channels if c.execution_plan and c.execution_plan.executor_kind == 'multimodal' and c.task_mode == 'natural_language']
        if len(requested) + len(multimodal) != len(config.channels) or any(c not in chosen for c in requested):
            raise Error(502, 'provider_contract_invalid', '能力服务没有确认全部模型/模板引用，不能发布。')
    service.lock_write(db)
    db.expire_all()
    revision = service.get_revision(db, revision_id)
    writable(service.get_agent(db, revision.agent_id))
    service.check_version(revision, expected_version)
    if revision.state != 'draft' or digest(revision.config) != config_hash or digest(source_snapshots(db, config)) != sources_hash:
        raise Error(409, 'validation_stale', '验证期间配置或视频源发生变化，请重新验证。')
    value = AgentValidation(revision_id=revision.id, config_hash=config_hash, source_hash=sources_hash,
                            capability_fingerprint=assessment.capability_fingerprint, verdict=assessment.verdict,
                            result=assessment.model_dump(mode='json'), data_origin=assessment.data_origin,
                            expires_at=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat().replace('+00:00', 'Z'))
    db.add(value); db.flush()
    revision.latest_validation_id = value.id
    revision.row_version += 1
    db.flush()
    return validation_dto(value)


def confirm(db, revision_id, body, provider, actor_id, key):
    # Fingerprint lookup is an external service call, before the write lock.
    existing, _ = service.receipt(db, actor_id, key, f'confirm:{revision_id}', body.model_dump(mode='json'))
    if existing:
        return RevisionDTO.model_validate(existing.response)
    db.rollback()
    catalog = provider.catalog(actor_id)
    service.lock_write(db)
    existing, request_hash = service.receipt(db, actor_id, key, f'confirm:{revision_id}', body.model_dump(mode='json'))
    if existing:
        return RevisionDTO.model_validate(existing.response)
    revision = service.get_revision(db, revision_id)
    agent = service.get_agent(db, revision.agent_id)
    writable(agent)
    service.check_version(revision, body.row_version)
    value = get_validation(db, body.validation_id)
    if revision.state != 'draft' or value.revision_id != revision.id or revision.latest_validation_id != value.id:
        raise Error(409, 'validation_stale', '请选择此草稿最新的验证结果。')
    if value.verdict != 'executable':
        raise Error(422, 'validation_blocked', '仍有未满足条件，不能确认发布。', value.result)
    if not body.limitations_acknowledged:
        raise Error(422, 'confirmation_required', '请核对完整配置及能力限制并明确确认。')
    if (value.expires_at <= now() or value.config_hash != digest(revision.config) or body.config_hash != value.config_hash
            or value.source_hash != digest(source_snapshots(db, RevisionDTO.model_validate(revision).config))
            or catalog.fingerprint != value.capability_fingerprint or value.data_origin != provider.data_origin):
        raise Error(409, 'validation_stale', '配置、视频源、能力版本发生变化或验证已过期，请重新验证。')
    db.add(AgentConfirmation(revision_id=revision.id, validation_id=value.id, actor_id=actor_id,
                            config_hash=value.config_hash, limitations_acknowledged=True))
    revision.state = 'published'; revision.published_at = now(); revision.row_version += 1
    agent.desired_revision_id = revision.id; agent.row_version += 1; agent.updated_at = now()
    db.add(Log(level='INFO', module='agents', message=f'用户 {actor_id} 确认发布配置 {revision.id}。'))
    db.flush()
    result = RevisionDTO.model_validate(revision)
    db.add(AgentCommand(actor_id=actor_id, command_key=key, request_hash=request_hash, response=result.model_dump(mode='json')))
    return result


def scoped_run(db, provider, agent_id, run_id, actor_id):
    service.get_agent(db, agent_id)
    run = next((r for r in provider.runs(agent_id, actor_id) if r.id == run_id), None)
    if not run or run.agent_id != agent_id:
        raise Error(404, 'run_not_found', '该智能体中不存在这次运行。')
    revision = service.get_revision(db, run.revision_id)
    if revision.agent_id != agent_id:
        raise Error(502, 'provider_contract_invalid', '运行服务返回的配置关联不一致。')
    return run


def start(db, provider, agent_id, body, actor_id, key, kind='start'):
    operation_name = f'run:{kind}:{agent_id}'
    payload = body.model_dump(mode='json')
    existing, _ = service.receipt(db, actor_id, key, operation_name, payload)
    if existing:
        return provider.operation(agent_id, existing.response['id'], actor_id)
    agent = service.get_agent(db, agent_id); writable(agent)
    revision = service.get_revision(db, body.revision_id)
    if revision.agent_id != agent_id or revision.state != 'published':
        raise Error(422, 'published_revision_required', '请先验证并确认发布此智能体的配置。')
    confirmation = db.scalar(select(AgentConfirmation).where(AgentConfirmation.revision_id == revision.id))
    if not confirmation:
        raise Error(422, 'confirmation_required', '配置缺少有效的用户确认记录。')
    validation = get_validation(db, confirmation.validation_id)
    config = RevisionDTO.model_validate(revision).config
    check_group_support(provider, config)
    sources = source_snapshots(db, config)
    if validation.expires_at <= now() or validation.config_hash != digest(revision.config) or validation.source_hash != digest(sources):
        raise Error(409, 'validation_stale', '执行依据已经改变，请复制为草稿后重新验证确认。')
    if not set(body.channel_ids) <= {c.channel_id for c in config.channels}:
        raise Error(422, 'invalid_channel_scope', '启动范围包含此版本中不存在的通道。')
    catalog = provider.catalog(actor_id)
    if catalog.fingerprint != validation.capability_fingerprint or provider.data_origin != validation.data_origin:
        raise Error(409, 'validation_stale', '能力版本发生变化，请重新验证确认。')
    provider.verify_execution_plans(config, actor_id)
    command = RuntimeCommand(kind=kind, agent_id=agent_id, revision_id=revision.id, revision_no=revision.revision_no,
                             config=config, channel_ids=body.channel_ids, expected_active_run_ids=body.expected_active_run_ids,
                             validation_id=validation.id, confirmation_id=confirmation.id,
                             capability_fingerprint=validation.capability_fingerprint, baseline_run_id=revision.baseline_run_id,
                             source_kinds={s['id']: s['kind'] for s in sources}, source_snapshots=sources)
    # Runtime provider must atomically compare actual runs, lock scope and recheck resources.
    result = provider.submit(command, actor_id, key)
    if result.agent_id != agent_id or result.data_origin != provider.data_origin:
        raise Error(502, 'provider_contract_invalid', '运行服务返回的操作关联或来源标记不一致。')
    return remember_operation(db, result, actor_id, key, operation_name, payload)


def remember_operation(db, result, actor_id, key, operation_name, payload):
    if result.data_origin not in ('real', 'mock'):
        raise Error(502, 'provider_contract_invalid', '运行操作的数据来源标记无效。')
    service.lock_write(db)
    existing, request_hash = service.receipt(db, actor_id, key, operation_name, payload)
    if existing:
        return OperationDTO.model_validate(existing.response)
    db.add(AgentCommand(actor_id=actor_id, command_key=key, request_hash=request_hash, response=result.model_dump(mode='json')))
    return result


def stop(db, provider, agent_id, run_id, actor_id, key):
    operation_name = f'run:stop:{agent_id}'
    payload = {'run_id': run_id}
    existing, _ = service.receipt(db, actor_id, key, operation_name, payload)
    if existing:
        return provider.operation(agent_id, existing.response['id'], actor_id)
    run = scoped_run(db, provider, agent_id, run_id, actor_id)
    result = provider.submit(RuntimeCommand(kind='stop', agent_id=agent_id, stop_run_id=run.id, channel_ids=[run.channel_id]), actor_id, key)
    if result.agent_id != agent_id or result.data_origin != provider.data_origin:
        raise Error(502, 'provider_contract_invalid', '停止操作关联或来源标记不一致。')
    return remember_operation(db, result, actor_id, key, operation_name, payload)


def stop_channel(db, provider, agent_id, channel_id, actor_id, key):
    operation_name = f'channel:stop:{agent_id}'
    payload = {'channel_id': channel_id}
    existing, _ = service.receipt(db, actor_id, key, operation_name, payload)
    if existing:
        return provider.operation(agent_id, existing.response['id'], actor_id)
    service.get_agent(db, agent_id)
    targets = [r for r in provider.runs(agent_id, actor_id) if r.channel_id == channel_id and r.state in ACTIVE_STATES]
    if not targets:
        raise Error(409, 'run_scope_changed', '该通道当前没有活动运行，请刷新后查看。')
    if not provider.supports_grouped_sources and len(targets) > 1:
        raise Error(503, 'grouped_sources_unavailable', '运行服务尚未支持通道停止。')
    if any(r.agent_id != agent_id for r in targets):
        raise Error(502, 'provider_contract_invalid', '运行服务返回了其他智能体的数据。')
    result = provider.submit(RuntimeCommand(kind='stop', agent_id=agent_id, channel_ids=[channel_id],
        stop_channel_id=channel_id if provider.supports_grouped_sources else None, stop_run_id=None if provider.supports_grouped_sources else targets[0].id,
        expected_active_run_ids=[r.id for r in targets]), actor_id, key)
    if result.agent_id != agent_id or result.data_origin != provider.data_origin:
        raise Error(502, 'provider_contract_invalid', '停止操作关联不一致。')
    return remember_operation(db, result, actor_id, key, operation_name, payload)


def workspace(db, provider, agent_id, actor_id):
    service.get_agent(db, agent_id)
    try:
        runs = provider.runs(agent_id, actor_id)
        if any(r.agent_id != agent_id or r.data_origin != provider.data_origin for r in runs):
            raise Error(502, 'provider_contract_invalid', '运行服务返回了不属于此智能体的数据。')
        for run in runs:
            revision = service.get_revision(db, run.revision_id)
            if revision.agent_id != agent_id or revision.revision_no != run.revision_no or digest(revision.config) != digest(run.config_snapshot.model_dump(mode='json')) or not any(c.get('channel_id') == run.channel_id and any(b.source_id == run.source_id for b in channel_sources(c)) for c in revision.config['channels']):
                raise Error(502, 'provider_contract_invalid', '实际运行配置与发布版本不一致。')
        return WorkspaceDTO(agent_id=agent_id, runs=runs, runtime_available=True, observed_at=now(), data_origin=provider.data_origin)
    except Error as exc:
        if exc.status != 503:
            raise
        return WorkspaceDTO(agent_id=agent_id, runs=[], runtime_available=False, runtime_error=exc.message, observed_at=now(), data_origin=provider.data_origin)


def enrich(db, dto, provider, actor_id):
    dto.data_origin = provider.data_origin
    if dto.archived_at:
        dto.status = 'archived'; return dto
    w = workspace(db, provider, dto.id, actor_id)
    states = {r.state for r in w.runs}
    active = [r for r in w.runs if r.state in ACTIVE_STATES]
    dto.active_run_count = len(active) if w.runtime_available else None
    dto.active_revision_nos = sorted({r.revision_no for r in active})
    latest = {}
    for r in sorted(w.runs, key=lambda r: r.created_at or r.started_at or '', reverse=True):
        latest.setdefault((r.channel_id, r.source_id), r)
    dto.failed_run_count = sum(r.state == 'failed' for r in latest.values()) if w.runtime_available else None
    if active:
        if any(r.state in ('running', 'reconnecting') and (not r.last_heartbeat_at or (datetime.now(timezone.utc)-datetime.fromisoformat(r.last_heartbeat_at.replace('Z', '+00:00'))).total_seconds() > 30) for r in active):
            dto.status = 'unknown'
        else:
            dto.status = next((state for state in ('running', 'stopping', 'queued') if any(r.state in ({'running', 'reconnecting'} if state == 'running' else {'queued', 'starting'} if state == 'queued' else {'stopping'}) for r in active)), 'unknown')
    elif w.runs:
        dto.status = 'failed' if any(r.state == 'failed' for r in latest.values()) else 'stopped'
    elif dto.desired_revision_id:
        dto.status = 'ready' if w.runtime_available else 'unknown'
    else:
        dto.status = 'draft'
    try:
        page = provider.events(dto.id, actor_id, {'limit': 100})
        dto.latest_event_at = max((e.occurred_at for e in page.items), default=None)
        dto.today_event_count = page.today_count
        dto.pending_review_count = page.pending_review_count
        # Provider summary is authoritative; do not infer total counts from a page.
    except Error as exc:
        if exc.status != 503:
            raise
    if hasattr(dto, 'execution_available'):
        dto.execution_available = provider.available('runtime') and provider.available('capability')
        dto.limitation = ('演示模式：所有运行、画面和报警均为模拟，不代表实际识别效果。' if provider.data_origin == 'mock'
                          else '运行状态由公共服务确认；未接入或故障的服务将单独提示。')
    return dto


def archive(db, provider, agent_id, expected_version, actor_id, restore=False):
    agent = service.get_agent(db, agent_id)
    # Published definitions might be running even when a service is down: fail closed.
    published = any(r.state == 'published' for r in service.revisions_for(db, agent_id))
    service.check_version(agent, expected_version)
    if published:
        provider.set_archived(agent_id, not restore, actor_id)
    service.lock_write(db); db.expire_all()
    agent = service.get_agent(db, agent_id)
    try:
        service.check_version(agent, expected_version)
    except Error:
        if published:
            provider.set_archived(agent_id, bool(agent.archived_at), actor_id)
        raise
    agent.archived_at = None if restore else now(); agent.updated_at = now(); agent.row_version += 1
    db.flush()
    return service.agent_dto(db, agent, detail=True)


def retest(db, provider, agent_id, body, actor_id, key):
    run = scoped_run(db, provider, agent_id, body.baseline_run_id, actor_id)
    if run.state in ACTIVE_STATES:
        raise Error(409, 'baseline_running', '请先结束基线运行，再创建可追溯的复测草稿。')
    result = service.clone_revision(db, agent_id, RevisionClone(base_revision_id=run.revision_id, row_version=body.row_version), actor_id, key, baseline_run_id=run.id, baseline_channel_id=run.channel_id, baseline_source_id=run.source_id)
    return result
