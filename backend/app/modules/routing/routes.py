"""Routing state, decisions and the observation-driven switch."""
from fastapi import APIRouter, Depends, Query

from ...shared.db import get_db
from ..agents.workspace import WORKSPACE_ACTOR_ID
from . import service, state
from .schemas import (CancelInput, ProposeInput, RouteDecisionView, RouteStateView,
                      RouteView)

router = APIRouter(tags=['routing'])


@router.get('/sources/{source_id}/routes', response_model=RouteView)
def read_routes(source_id: str,
                rule: str = Query('absence', pattern='^(absence|intrusion)$'),
                duration_seconds: float | None = Query(None, gt=0, le=86400,
                                                       allow_inf_nan=False),
                min_quality: float | None = Query(None, ge=0, le=1, allow_inf_nan=False),
                db=Depends(get_db)):
    extra = {} if min_quality is None else {'min_quality': min_quality}
    return service.evaluate_route(db, source_id, rule, duration_seconds=duration_seconds,
                                  **extra)


@router.get('/agents/{agent_id}/routing', response_model=list[RouteStateView])
def read_states(agent_id: str, db=Depends(get_db)):
    return state.list_states(db, agent_id, WORKSPACE_ACTOR_ID)


@router.get('/agents/{agent_id}/routing/decisions', response_model=list[RouteDecisionView])
def read_decisions(agent_id: str,
                   channel_id: str | None = Query(None, min_length=1, max_length=80),
                   source_id: str | None = Query(None, min_length=1, max_length=80),
                   limit: int = Query(30, ge=1, le=200),
                   db=Depends(get_db)):
    return state.decisions(db, agent_id, WORKSPACE_ACTOR_ID, channel_id=channel_id,
                           source_id=source_id, limit=limit)


@router.post('/agents/{agent_id}/routing/propose', response_model=RouteStateView)
def propose(agent_id: str, body: ProposeInput, db=Depends(get_db)):
    return state.propose(db, agent_id, WORKSPACE_ACTOR_ID, channel_id=body.channel_id,
                         source_id=body.source_id, rule=body.rule,
                         duration_seconds=body.duration_seconds)


@router.post('/agents/{agent_id}/routing/cancel', response_model=RouteStateView)
def cancel(agent_id: str, body: CancelInput, db=Depends(get_db)):
    return state.cancel_candidate(db, agent_id, WORKSPACE_ACTOR_ID,
                                 channel_id=body.channel_id, source_id=body.source_id)
