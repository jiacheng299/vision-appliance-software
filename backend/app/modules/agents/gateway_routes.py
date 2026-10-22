"""B-facing façade over public providers. It never writes their databases."""
import asyncio
from datetime import datetime, timezone
import json
from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import Response, StreamingResponse
from ...shared.db import get_db
from ...shared.errors import Error
from ...shared.models import Session, User, now
from ...shared.security import digest as secret_digest
from ..auth import current_user, writer
from . import service, workflow
from .contracts import *
from .schemas import AgentDetail, RevisionDTO

router = APIRouter(tags=['agent-workflow'])


def providers(request: Request):
    return request.app.state.agent_services


def event_scope(db, provider, agent_id, event_id, actor_id):
    service.get_agent(db, agent_id)
    event = provider.event(agent_id, event_id, actor_id)
    revision = service.get_revision(db, event.revision_id)
    if event.agent_id != agent_id or revision.agent_id != agent_id or not any(c.get('channel_id') == event.channel_id and c.get('source_id') == event.source_id for c in revision.config['channels']):
        raise Error(502, 'provider_contract_invalid', '事件的源、通道或版本关联不一致。')
    return event


@router.get('/agent-environment', response_model=EnvironmentDTO)
def environment(provider=Depends(providers)):
    return EnvironmentDTO(data_origin=provider.data_origin, message='独立演示模式：运行、画面、报警和导出均为模拟，重启后模拟运行记录会重置。' if provider.data_origin == 'mock' else '真实模式：仅展示公共服务实际返回的状态与结果。')


@router.get('/agent-services/capabilities', response_model=CapabilityCatalog)
def capabilities(user=Depends(current_user), provider=Depends(providers)):
    return provider.catalog(user.id)


@router.get('/agent-services/references', response_model=ReferencePage)
def references(source_id: str | None = Query(None, max_length=80), model_id: str | None = Query(None, max_length=160),
               model_version: str | None = Query(None, max_length=80), cursor: str | None = Query(None, max_length=80),
               limit: int = Query(100, ge=1, le=100), user=Depends(current_user), db=Depends(get_db), provider=Depends(providers)):
    from sqlalchemy import select
    from .models import AgentRevision
    if not source_id and not model_id:
        raise Error(422, 'validation_error', '请指定要查询引用的视频源或模型。')
    query = select(AgentRevision).order_by(AgentRevision.id)
    if cursor:
        query = query.where(AgentRevision.id > cursor)
    result = []; run_cache = {}
    for revision in db.scalars(query):
        matches = []
        for channel in revision.config['channels']:
            ref = channel.get('capability_ref') or {}
            if source_id and channel.get('source_id') != source_id:
                continue
            if model_id and (ref.get('model_id') != model_id or (model_version and ref.get('model_version') != model_version)):
                continue
            matches.append(channel['channel_id'])
        if not matches:
            continue
        agent = service.get_agent(db, revision.agent_id)
        if agent.id not in run_cache:
            try:
                run_cache[agent.id] = provider.runs(agent.id, user.id)
            except Error as exc:
                if exc.status != 503:
                    raise
                run_cache[agent.id] = None
        runs = run_cache[agent.id]
        result.append(AgentReference(agent_id=agent.id, agent_name=agent.name, revision_id=revision.id, revision_no=revision.revision_no,
            revision_state=revision.state, channel_ids=matches, archived=bool(agent.archived_at), runtime_checked=runs is not None,
            active_run_ids=[r.id for r in runs if r.revision_id == revision.id and r.channel_id in matches and r.state in ACTIVE_STATES] if runs is not None else None))
        if len(result) > limit:
            break
    return ReferencePage(items=result[:limit], next_cursor=result[limit-1].revision_id if len(result)>limit else None, data_origin=provider.data_origin)


@router.get('/agents/{agent_id}/workspace', response_model=WorkspaceDTO)
def workspace(agent_id: str, user=Depends(current_user), db=Depends(get_db), provider=Depends(providers)):
    return workflow.workspace(db, provider, agent_id, user.id)


@router.get('/validations/{validation_id}', response_model=ValidationDTO)
def validation(validation_id: str, user=Depends(current_user), db=Depends(get_db)):
    return workflow.validation_dto(workflow.get_validation(db, validation_id))


@router.post('/revisions/{revision_id}/confirmations', response_model=RevisionDTO)
def confirm(revision_id: str, body: ConfirmationInput, idempotency_key: str = Header(min_length=1, max_length=128),
            user=Depends(writer), db=Depends(get_db), provider=Depends(providers)):
    return workflow.confirm(db, revision_id, body, provider, user.id, idempotency_key)


@router.post('/agents/{agent_id}/run-groups', response_model=OperationDTO, status_code=202)
def start(agent_id: str, body: StartInput, idempotency_key: str = Header(min_length=1, max_length=128),
          user=Depends(writer), db=Depends(get_db), provider=Depends(providers)):
    return workflow.start(db, provider, agent_id, body, user.id, idempotency_key)


@router.post('/agents/{agent_id}/revision-applications', response_model=OperationDTO, status_code=202)
def apply(agent_id: str, body: StartInput, idempotency_key: str = Header(min_length=1, max_length=128),
          user=Depends(writer), db=Depends(get_db), provider=Depends(providers)):
    return workflow.start(db, provider, agent_id, body, user.id, idempotency_key, kind='apply')


@router.post('/agents/{agent_id}/runs/{run_id}/stop', response_model=OperationDTO, status_code=202)
def stop(agent_id: str, run_id: str, idempotency_key: str = Header(min_length=1, max_length=128),
         user=Depends(writer), db=Depends(get_db), provider=Depends(providers)):
    return workflow.stop(db, provider, agent_id, run_id, user.id, idempotency_key)


@router.get('/agents/{agent_id}/operations/{operation_id}', response_model=OperationDTO)
def operation(agent_id: str, operation_id: str, user=Depends(current_user), db=Depends(get_db), provider=Depends(providers)):
    service.get_agent(db, agent_id)
    result = provider.operation(agent_id, operation_id, user.id)
    if result.agent_id != agent_id:
        raise Error(502, 'provider_contract_invalid', '操作关联不一致。')
    return result


@router.post('/agents/{agent_id}/archive', response_model=AgentDetail)
def archive(agent_id: str, body: VersionCommand, user=Depends(writer), db=Depends(get_db), provider=Depends(providers)):
    return workflow.archive(db, provider, agent_id, body.row_version, user.id)


@router.post('/agents/{agent_id}/restore', response_model=AgentDetail)
def restore(agent_id: str, body: VersionCommand, user=Depends(writer), db=Depends(get_db), provider=Depends(providers)):
    return workflow.archive(db, provider, agent_id, body.row_version, user.id, restore=True)


def iso_utc(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')
    except (ValueError, AttributeError):
        raise Error(422, 'invalid_time', '时间必须是带时区的 ISO8601 时间。')


@router.get('/agents/{agent_id}/events', response_model=AgentEventPage)
def events(agent_id: str, run_id: str | None = None, event_type: str | None = Query(None, max_length=160),
           review_status: str | None = Query(None, pattern='^(unreviewed|correct|false_positive)$'),
           from_time: str | None = None, to_time: str | None = None, cursor: str | None = Query(None, max_length=512),
           limit: int = Query(30, ge=1, le=100), user=Depends(current_user), db=Depends(get_db), provider=Depends(providers)):
    service.get_agent(db, agent_id)
    filters = dict(run_id=run_id, event_type=event_type, review_status=review_status, from_time=iso_utc(from_time) if from_time else None, to_time=iso_utc(to_time) if to_time else None, limit=limit)
    if filters['from_time'] and filters['to_time'] and filters['from_time'] > filters['to_time']:
        raise Error(422, 'invalid_time', '开始时间应早于结束时间。')
    page = provider.events(agent_id, user.id, filters, cursor=cursor)
    if any(e.agent_id != agent_id for e in page.items):
        raise Error(502, 'provider_contract_invalid', '事件查询返回了其他智能体的数据。')
    return page


@router.get('/agents/{agent_id}/event-stream')
def event_stream(agent_id: str, request: Request, after: str = Query('0', max_length=512), once: bool = False,
                 user=Depends(current_user), db=Depends(get_db), provider=Depends(providers)):
    service.get_agent(db, agent_id)
    if not provider.available('events'):
        provider.unavailable('events')
    actor_id = user.id; token = secret_digest(request.cookies.get('vision_session', ''))
    cursor = request.headers.get('last-event-id', after)
    if len(cursor) > 512:
        raise Error(422, 'invalid_cursor', '订阅游标无效。')
    db.rollback()
    async def stream():
        nonlocal cursor
        while not await request.is_disconnected():
            with request.app.state.sessions() as check_db:
                session = check_db.get(Session, token)
                actor = check_db.get(User, actor_id)
                if not session or session.expires_at <= now() or not actor or session.user_id != actor_id:
                    yield 'event: session_expired\ndata: {}\n\n'; return
            try:
                page = await asyncio.to_thread(provider.events, agent_id, actor_id, {'limit': 100}, None, cursor)
                if any(e.agent_id != agent_id for e in page.items):
                    raise Error(502, 'provider_contract_invalid', '订阅事件关联不一致。')
                kind = 'resync_required' if page.resync_required else 'events'
                cursor = page.stream_cursor
                if '\n' in cursor or '\r' in cursor:
                    raise Error(502, 'provider_contract_invalid', '订阅游标格式无效。')
                yield f'id: {cursor}\nevent: {kind}\ndata: {page.model_dump_json()}\n\n'
            except Error as exc:
                yield 'event: unavailable\ndata: '+json.dumps({'code': exc.code, 'message': exc.message}, ensure_ascii=False)+'\n\n'
                return
            if once:
                return
            await asyncio.sleep(1)
    return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})


@router.get('/agents/{agent_id}/events/{event_id}', response_model=EventDetail)
def event(agent_id: str, event_id: str, user=Depends(current_user), db=Depends(get_db), provider=Depends(providers)):
    return event_scope(db, provider, agent_id, event_id, user.id)


@router.post('/agents/{agent_id}/events/{event_id}/feedback', response_model=EventDetail)
def feedback(agent_id: str, event_id: str, body: FeedbackInput, idempotency_key: str = Header(min_length=1, max_length=128),
             user=Depends(writer), db=Depends(get_db), provider=Depends(providers)):
    event_scope(db, provider, agent_id, event_id, user.id)
    return provider.feedback(agent_id, event_id, body, user.id, idempotency_key)


@router.get('/agents/{agent_id}/missed-annotations', response_model=MissedPage)
def missed(agent_id: str, user=Depends(current_user), db=Depends(get_db), provider=Depends(providers)):
    service.get_agent(db, agent_id)
    return MissedPage(items=provider.missed(agent_id, user.id), data_origin=provider.data_origin)


@router.post('/agents/{agent_id}/missed-annotations', response_model=MissedDTO, status_code=201)
def add_missed(agent_id: str, body: MissedInput, idempotency_key: str = Header(min_length=1, max_length=128),
               user=Depends(writer), db=Depends(get_db), provider=Depends(providers)):
    run = workflow.scoped_run(db, provider, agent_id, body.run_id, user.id)
    if body.start_media_ms is not None or body.end_media_ms is not None:
        if run.source_kind == 'camera' and not run.recording_available:
            raise Error(422, 'invalid_media_range', '这次实时运行没有可定位的录像，请填写发生时间和描述。')
        lower = run.start_media_ms or 0
        upper = run.end_media_ms if run.end_media_ms is not None else lower+run.selected_duration_ms if run.selected_duration_ms is not None else None
        if upper is None:
            raise Error(422, 'invalid_media_range', '运行服务未提供可核对的录像范围，暂不能按区间补录。')
        if body.start_media_ms is None or body.end_media_ms is None or body.start_media_ms >= body.end_media_ms or body.start_media_ms < lower or (upper is not None and body.end_media_ms > upper):
            raise Error(422, 'invalid_media_range', '漏报区间应在本次运行的验证范围内，结束晚于开始。')
    elif run.source_kind == 'file':
        raise Error(422, 'invalid_media_range', '录像漏报必须填写起止位置。')
    elif not body.occurred_at:
        raise Error(422, 'invalid_time', '无录像的实时漏报必须填写发生时间。')
    if body.occurred_at:
        body.occurred_at = iso_utc(body.occurred_at)
        occurred = datetime.fromisoformat(body.occurred_at.replace('Z', '+00:00'))
        start_time = datetime.fromisoformat(run.started_at.replace('Z', '+00:00')) if run.started_at else None
        end_time = datetime.fromisoformat(run.ended_at.replace('Z', '+00:00')) if run.ended_at else datetime.now(timezone.utc)
        if (start_time and occurred < start_time) or occurred > end_time:
            raise Error(422, 'invalid_time', '发生时间应在该运行的开始与结束时间之间。')
    return provider.add_missed(run, body, user.id, idempotency_key)


@router.post('/agents/{agent_id}/runs/{run_id}/playback', response_model=PlaybackDTO)
def playback(agent_id: str, run_id: str, user=Depends(current_user), db=Depends(get_db), provider=Depends(providers)):
    run = workflow.scoped_run(db, provider, agent_id, run_id, user.id)
    return provider.playback(run, user.id)


@router.delete('/agents/{agent_id}/playback-sessions/{session_id}', response_model=EmptyResult)
def release_playback(agent_id: str, session_id: str, user=Depends(current_user), db=Depends(get_db), provider=Depends(providers)):
    service.get_agent(db, agent_id); provider.release_playback(agent_id, session_id, user.id)
    return EmptyResult()


@router.post('/agents/{agent_id}/events/{event_id}/evidence/{evidence_id}/access-sessions', response_model=PlaybackDTO)
def evidence(agent_id: str, event_id: str, evidence_id: str, user=Depends(current_user), db=Depends(get_db), provider=Depends(providers)):
    value = event_scope(db, provider, agent_id, event_id, user.id)
    if not any(e.id == evidence_id for e in value.evidence):
        raise Error(404, 'evidence_not_found', '该事件没有此证据。')
    return provider.evidence(agent_id, event_id, evidence_id, user.id)


@router.post('/agents/{agent_id}/retests', response_model=RevisionDTO, status_code=201)
def retest(agent_id: str, body: RetestInput, idempotency_key: str = Header(min_length=1, max_length=128),
           user=Depends(writer), db=Depends(get_db), provider=Depends(providers)):
    return workflow.retest(db, provider, agent_id, body, user.id, idempotency_key)


@router.get('/agents/{agent_id}/comparisons', response_model=ComparisonDTO)
def compare(agent_id: str, baseline_run_id: str, candidate_run_id: str, user=Depends(current_user), db=Depends(get_db), provider=Depends(providers)):
    baseline = workflow.scoped_run(db, provider, agent_id, baseline_run_id, user.id)
    candidate = workflow.scoped_run(db, provider, agent_id, candidate_run_id, user.id)
    if candidate.baseline_run_id != baseline.id:
        raise Error(422, 'invalid_baseline', '所选运行没有关联这次基线。')
    return provider.compare(baseline, candidate, user.id)


@router.post('/agents/{agent_id}/exports', response_model=ExportDTO, status_code=202)
def export(agent_id: str, body: ExportInput, idempotency_key: str = Header(min_length=1, max_length=128),
           user=Depends(writer), db=Depends(get_db), provider=Depends(providers)):
    if len(set(body.run_ids)) != len(body.run_ids) or len(set(body.contents)) != len(body.contents):
        raise Error(422, 'invalid_export_scope', '导出范围和内容不能重复。')
    for run_id in body.run_ids:
        workflow.scoped_run(db, provider, agent_id, run_id, user.id)
    destinations = provider.export_destinations(user.id)
    if not any(d.kind == body.destination and d.alias == body.destination_alias for d in destinations.items):
        raise Error(422, 'invalid_export_scope', '导出目的地不在当前账户允许的目录别名中。')
    return provider.export(agent_id, body, user.id, idempotency_key)


@router.get('/agent-services/export-destinations', response_model=ExportDestinations)
def export_destinations(user=Depends(current_user), provider=Depends(providers)):
    return provider.export_destinations(user.id)


@router.get('/agents/{agent_id}/exports/{export_id}', response_model=ExportDTO)
def export_status(agent_id: str, export_id: str, user=Depends(current_user), db=Depends(get_db), provider=Depends(providers)):
    service.get_agent(db, agent_id)
    return provider.export_status(agent_id, export_id, user.id)


@router.post('/agents/{agent_id}/exports/{export_id}/{action}', response_model=ExportDTO, status_code=202)
def export_action(agent_id: str, export_id: str, action: str, idempotency_key: str = Header(min_length=1, max_length=128),
                  user=Depends(writer), db=Depends(get_db), provider=Depends(providers)):
    if action not in ('cancel', 'retry'):
        raise Error(404, 'not_found', '操作不存在。')
    service.get_agent(db, agent_id)
    return provider.export_action(agent_id, export_id, action, user.id, idempotency_key)


@router.get('/agents/{agent_id}/exports/{export_id}/download')
def export_download(agent_id: str, export_id: str, user=Depends(current_user), db=Depends(get_db), provider=Depends(providers)):
    service.get_agent(db, agent_id)
    name, media_type, content = provider.export_download(agent_id, export_id, user.id)
    from urllib.parse import quote
    name = name.replace('\\', '/').split('/')[-1]
    name = ''.join(c for c in name if ord(c) >= 32) or 'export.bin'
    return Response(content, media_type=media_type, headers={'Content-Disposition': "attachment; filename*=UTF-8''"+quote(name, safe='')})


@router.post('/agent-demo/seed', response_model=AgentDetail)
def seed(user=Depends(writer), db=Depends(get_db), provider=Depends(providers)):
    from .demo import DemoServices, seed_demo
    if not isinstance(provider, DemoServices):
        raise Error(404, 'not_found', '当前模式不提供演示数据。')
    result = seed_demo(db, user.id)
    return workflow.enrich(db, AgentDetail.model_validate(result), provider, user.id)


@router.post('/agent-demo/scenario', response_model=EnvironmentDTO)
def demo_scenario(body: DemoScenario, user=Depends(writer), provider=Depends(providers)):
    from .demo import DemoServices
    if not isinstance(provider, DemoServices):
        raise Error(404, 'not_found', '当前模式不提供模拟故障。')
    provider.set_scenario(body.scenario, body.run_id)
    return EnvironmentDTO(data_origin='mock', message='已切换模拟情形：'+body.scenario)
