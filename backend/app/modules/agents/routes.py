from fastapi import APIRouter, Depends, Header, Query
from ...shared.db import get_db
from ...shared.errors import Error
from .workspace import WORKSPACE_ACTOR_ID
from . import service
from .schemas import AgentCreate, AgentDetail, AgentPage, AgentPatch, RevisionClone, RevisionDTO, RevisionPatch
from .contracts import ValidationDTO, VersionCommand
from .gateway_routes import providers
from . import workflow

router = APIRouter(tags=['agents'])


@router.get('/agents', response_model=AgentPage)
def list_agents(q: str = Query('', max_length=160), source_id: str | None = None,
                cursor: str | None = Query(None, max_length=512), limit: int = Query(24, ge=1, le=100),
                status: str | None = Query(None, pattern='^(draft|ready|queued|running|stopping|stopped|failed|unknown|archived)$'), scene: str | None = Query(None, max_length=160), archived: bool = False,
                sort: str = Query('updated_desc', pattern='^(updated_desc|name_asc)$'),
                db=Depends(get_db), provider=Depends(providers)):
    return service.list_agents(db, q, source_id, cursor, limit, archived=archived, provider=provider, actor_id=WORKSPACE_ACTOR_ID, status=status, scene=scene, sort=sort)


@router.post('/agents', response_model=AgentDetail, status_code=201)
def create_agent(body: AgentCreate, idempotency_key: str = Header(min_length=1, max_length=128), db=Depends(get_db)):
    return service.create_agent(db, body, WORKSPACE_ACTOR_ID, idempotency_key)


@router.get('/agents/{agent_id}', response_model=AgentDetail)
def agent_detail(agent_id: str, db=Depends(get_db), provider=Depends(providers)):
    return workflow.enrich(db, service.agent_dto(db, service.get_agent(db, agent_id), detail=True), provider, WORKSPACE_ACTOR_ID)


@router.patch('/agents/{agent_id}', response_model=AgentDetail)
def patch_agent(agent_id: str, body: AgentPatch, db=Depends(get_db)):
    return service.patch_agent(db, agent_id, body)


@router.post('/agents/{agent_id}/revisions', response_model=RevisionDTO, status_code=201)
def clone_revision(agent_id: str, body: RevisionClone, idempotency_key: str = Header(min_length=1, max_length=128), db=Depends(get_db)):
    return service.clone_revision(db, agent_id, body, WORKSPACE_ACTOR_ID, idempotency_key)


@router.get('/revisions/{revision_id}', response_model=RevisionDTO)
def revision_detail(revision_id: str, db=Depends(get_db)):
    return service.get_revision(db, revision_id)


@router.patch('/revisions/{revision_id}', response_model=RevisionDTO)
def patch_revision(revision_id: str, body: RevisionPatch, db=Depends(get_db)):
    return service.patch_revision(db, revision_id, body)


@router.post('/revisions/{revision_id}/validations', response_model=ValidationDTO, status_code=201)
def validate_revision(revision_id: str, body: VersionCommand | None = None, db=Depends(get_db), provider=Depends(providers)):
    revision = service.get_revision(db, revision_id)
    return workflow.validate(db, revision_id, body.row_version if body else revision.row_version, provider, WORKSPACE_ACTOR_ID)
