"""Read and maintain the semantic profile; judge observation windows."""
from fastapi import APIRouter, Depends, Path, Query, Request

from ...shared.db import get_db
from ...shared.storage import controlled_path
from ..agents.workspace import WORKSPACE_ACTOR_ID
from . import bootstrap as bootstrap_module, service
from .schemas import (AttributeInput, BootstrapView, IntrinsicInput, ObservationInput,
                      ObservationPage, ObservationView, ProfileEventView, ProfileView)

router = APIRouter(tags=['semantics'])

KEY = Path(..., min_length=1, max_length=64)


@router.get('/sources/{source_id}/semantic-profile', response_model=ProfileView)
def read_profile(source_id: str, at: float | None = Query(None, ge=0, allow_inf_nan=False),
                 db=Depends(get_db)):
    return service.read_profile(db, source_id, at)


@router.put('/sources/{source_id}/semantic-profile', response_model=ProfileView)
def update_intrinsic(source_id: str, body: IntrinsicInput, db=Depends(get_db)):
    return service.update_intrinsic(db, source_id, body)


@router.put('/sources/{source_id}/semantic-profile/attributes/{key}', response_model=ProfileView)
def upsert_attribute(source_id: str, body: AttributeInput, key: str = KEY, db=Depends(get_db)):
    return service.upsert_attribute(db, source_id, key, body)


@router.delete('/sources/{source_id}/semantic-profile/attributes/{key}', response_model=ProfileView)
def delete_attribute(source_id: str, key: str = KEY, db=Depends(get_db)):
    return service.delete_attribute(db, source_id, key)


@router.post('/agents/{agent_id}/observations', response_model=ObservationView, status_code=201)
def record_observation(agent_id: str, body: ObservationInput, db=Depends(get_db)):
    return service.record_observation(db, agent_id, WORKSPACE_ACTOR_ID, body)


@router.get('/agents/{agent_id}/observations', response_model=ObservationPage)
def list_observations(agent_id: str,
                      source_id: str | None = Query(None, min_length=1, max_length=80),
                      verdict: str | None = Query(None, pattern='^(detected|not_detected|insufficient)$'),
                      run_id: str | None = Query(None, min_length=1, max_length=80),
                      task_key: str | None = Query(None, min_length=1, max_length=160),
                      limit: int = Query(50, ge=1, le=200),
                      cursor: str | None = Query(None, max_length=64),
                      db=Depends(get_db)):
    return service.list_observations(db, agent_id, WORKSPACE_ACTOR_ID, source_id=source_id,
                                     verdict=verdict, run_id=run_id, task_key=task_key,
                                     limit=limit, cursor=cursor)


@router.post('/sources/{source_id}/semantic-profile/bootstrap', response_model=BootstrapView)
def bootstrap_profile(source_id: str, request: Request,
                      from_recording: bool = Query(True, description='是否从本地录像取一帧测亮度'),
                      db=Depends(get_db)):
    """First-run profile initialisation: fill only what is missing."""
    from .. import sources as sources_module
    frame = None
    notices_extra = []
    source = sources_module.get_source(db, source_id)
    if from_recording and source.kind == 'file' and source.media_key:
        try:
            path = controlled_path(request.app.state.config, 'media', source.media_key)
            frame = bootstrap_module.sample_frame(path)
        except Exception:
            frame = None
        if frame is None:
            notices_extra.append('录像取帧失败，动态层保持为空。')
    elif source.kind != 'file':
        notices_extra.append('摄像头源不做首帧取图，动态层需由运行中的观察或人工写入。')
    result = bootstrap_module.bootstrap(db, source_id, frame=frame)
    result['notices'] = notices_extra + result['notices']
    return BootstrapView(**result)

@router.get('/sources/{source_id}/semantic-profile/events', response_model=list[ProfileEventView])
def list_profile_events(source_id: str,
                        limit: int = Query(50, ge=1, le=200),
                        db=Depends(get_db)):
    return service.list_events(db, source_id, limit=limit)