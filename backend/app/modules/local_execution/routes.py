"""Protected evidence access through the agent's existing event/run scope checks."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from ...shared.db import get_db
from ...shared.errors import Error
from ..agents import gateway_routes
from ..agents.workspace import WORKSPACE_ACTOR_ID

router = APIRouter(tags=['local-execution'])


@router.get('/agents/{agent_id}/events/{event_id}/evidence/{evidence_id}/media',response_class=FileResponse)
def evidence_media(agent_id:str,event_id:str,evidence_id:str,request:Request,db=Depends(get_db)):
    provider = request.app.state.agent_services
    gateway_routes.event_scope(db,provider,agent_id,event_id,WORKSPACE_ACTOR_ID)
    if not hasattr(provider,'evidence_file'):
        raise Error(503,'events_service_unavailable','真实截图证据服务尚未接入。')
    path = provider.evidence_file(agent_id,event_id,evidence_id,WORKSPACE_ACTOR_ID)
    return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'no-store'})
