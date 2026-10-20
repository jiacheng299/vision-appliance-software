from fastapi import APIRouter, Depends, Header, Query
from ...shared.db import get_db
from ...shared.errors import Error
from ..auth import current_user, writer
from . import service
from .schemas import AgentCreate, AgentDetail, AgentPage, AgentPatch, RevisionClone, RevisionDTO, RevisionPatch

router = APIRouter(tags=['agents'])


@router.get('/agents', response_model=AgentPage)
def list_agents(q: str = Query('', max_length=160), source_id: str | None = None,
                cursor: str | None = Query(None, max_length=512), limit: int = Query(24, ge=1, le=100),
                user=Depends(current_user), db=Depends(get_db)):
    return service.list_agents(db, q, source_id, cursor, limit)


@router.post('/agents', response_model=AgentDetail, status_code=201)
def create_agent(body: AgentCreate, idempotency_key: str = Header(min_length=1, max_length=128), user=Depends(writer), db=Depends(get_db)):
    return service.create_agent(db, body, user.id, idempotency_key)


@router.get('/agents/{agent_id}', response_model=AgentDetail)
def agent_detail(agent_id: str, user=Depends(current_user), db=Depends(get_db)):
    return service.agent_dto(db, service.get_agent(db, agent_id), detail=True)


@router.patch('/agents/{agent_id}', response_model=AgentDetail)
def patch_agent(agent_id: str, body: AgentPatch, user=Depends(writer), db=Depends(get_db)):
    return service.patch_agent(db, agent_id, body)


@router.post('/agents/{agent_id}/revisions', response_model=RevisionDTO, status_code=201)
def clone_revision(agent_id: str, body: RevisionClone, idempotency_key: str = Header(min_length=1, max_length=128), user=Depends(writer), db=Depends(get_db)):
    return service.clone_revision(db, agent_id, body, user.id, idempotency_key)


@router.get('/revisions/{revision_id}', response_model=RevisionDTO)
def revision_detail(revision_id: str, user=Depends(current_user), db=Depends(get_db)):
    return service.get_revision(db, revision_id)


@router.patch('/revisions/{revision_id}', response_model=RevisionDTO)
def patch_revision(revision_id: str, body: RevisionPatch, user=Depends(writer), db=Depends(get_db)):
    return service.patch_revision(db, revision_id, body)


@router.post('/revisions/{revision_id}/validations', response_model=RevisionDTO)
def validate_revision(revision_id: str, user=Depends(writer), db=Depends(get_db)):
    service.get_revision(db, revision_id)
    raise Error(503, 'capability_service_unavailable', '模型能力校验与需求评估服务尚未接入。草稿已保留，暂不能验证或启动。', retryable=True)
