"""Scoped access to local execution evidence and diagnostics."""
from contextlib import nullcontext
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from ...shared.db import get_db
from ...shared.errors import Error
from ..agents import gateway_routes
from ..agents.service import get_agent
from ..agents.workspace import WORKSPACE_ACTOR_ID
from .models import LocalEvent, LocalRun
from .trust_checks import RECORDS_LIMIT, TrustCheckDTO, read_trust_checks

router = APIRouter(tags=['local-execution'])


@router.get('/agents/{agent_id}/trust-checks', response_model=list[TrustCheckDTO])
def trust_checks(agent_id: str, request: Request,
                 source_id: str | None = Query(None, min_length=1, max_length=80), db=Depends(get_db)):
    get_agent(db, agent_id)
    provider = request.app.state.agent_services
    if provider.data_origin != 'real':
        return []
    audit = getattr(provider, 'safety_audit', None)
    try:
        with audit.read_access() if audit is not None else nullcontext():
            candidates = read_trust_checks(request.app.state.config.var_root, agent_id, source_id)
    except TimeoutError:
        raise Error(503, 'trust_checks_unavailable', '可信检查日志正在写入，请稍后刷新。', retryable=True) from None
    if not candidates:
        return []
    runs = {
        run_id: (source, channel, kind)
        for run_id, source, channel, kind in db.execute(
            select(LocalRun.id, LocalRun.source_id, LocalRun.channel_id, LocalRun.payload['source_kind'].as_string())
            .where(LocalRun.agent_id == agent_id, LocalRun.actor_id == WORKSPACE_ACTOR_ID,
                   LocalRun.id.in_({record.run_id for record in candidates}))
        )
    }
    records = [row for row in candidates
               if runs.get(row.run_id) == (row.source_id, row.channel_id, row.source_kind)][:RECORDS_LIMIT]
    event_ids = {row.event_id for row in records if row.event_id}
    if event_ids:
        event_runs = dict(db.execute(select(LocalEvent.id, LocalEvent.run_id)
            .where(LocalEvent.agent_id == agent_id, LocalEvent.actor_id == WORKSPACE_ACTOR_ID,
                   LocalEvent.id.in_(event_ids))).all())
        for row in records:
            if row.event_id and event_runs.get(row.event_id) != row.run_id:
                row.event_id = None
    return records


@router.get('/agents/{agent_id}/events/{event_id}/evidence/{evidence_id}/media',response_class=FileResponse)
def evidence_media(agent_id:str,event_id:str,evidence_id:str,request:Request,db=Depends(get_db)):
    provider = request.app.state.agent_services
    gateway_routes.event_scope(db,provider,agent_id,event_id,WORKSPACE_ACTOR_ID)
    if not hasattr(provider,'evidence_file'):
        raise Error(503,'events_service_unavailable','真实截图证据服务尚未接入。')
    path = provider.evidence_file(agent_id,event_id,evidence_id,WORKSPACE_ACTOR_ID)
    return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'no-store'})
