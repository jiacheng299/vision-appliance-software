"""Read the evaluated route candidates for one source and rule."""
from fastapi import APIRouter, Depends, Query

from ...shared.db import get_db
from . import service
from .schemas import RouteView

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
