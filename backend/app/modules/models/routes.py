"""A-owned APIs use snake_case and existing bare DTOs, matching this repository."""
import hashlib
import shutil
import uuid
import httpx
from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import select, or_
from ...shared.db import get_db
from ...shared.errors import Error
from ...shared.models import now
from ..agents.schemas import channel_sources
from ..agents.contracts import Assessment, CapabilityItem
from ..sources import resolve_agent_source
from .models import ModelFile, ModelPair, LLMSelection
from .schemas import *
from . import service

router = APIRouter(tags=['member-a'])


def adapter(request: Request):
    return request.app.state.model_services


def registry(request: Request):
    # The composition root supplies the same catalog used by B's validator.
    return request.app.state.agent_services.catalog('local-workspace')


@router.post('/model-files', response_model=ModelFileDTO, status_code=201)
async def upload_file(request: Request, filename: str = Query(min_length=1, max_length=240), db=Depends(get_db)):
    from ...schemas import UploadCreate
    from pydantic import ValidationError
    try:
        UploadCreate(filename=filename, size_bytes=1)
    except ValidationError:
        raise Error(422, 'validation_error', '模型文件名须为不含目录的普通文件名。')
    config = request.app.state.config
    root = config.var_root / 'model-files'; root.mkdir(exist_ok=True)
    identifier = str(uuid.uuid4()); partial = root / (identifier + '.part'); path = root / identifier
    size, hasher = 0, hashlib.sha256()
    try:
        with partial.open('xb') as stream:
            async for chunk in request.stream():
                size += len(chunk)
                if size > config.max_model_file_bytes:
                    raise Error(413, 'model_file_too_large', '模型文件超过当前大小上限。')
                if shutil.disk_usage(root).free < len(chunk) + 32 * 1024 * 1024:
                    raise Error(409, 'storage_low', '磁盘可用空间不足，请清理后重试。')
                stream.write(chunk); hasher.update(chunk)
        if not size:
            raise Error(422, 'model_file_empty', '模型文件不能为空。')
        partial.replace(path)
        value = ModelFile(id=identifier, filename=filename, size_bytes=size, checksum=hasher.hexdigest())
        db.add(value); db.flush(); db.commit()
        return ModelFileDTO.model_validate(value)
    except BaseException:
        partial.unlink(missing_ok=True); path.unlink(missing_ok=True)
        raise


@router.get('/models', response_model=ModelPage)
def list_models(q: str = Query('', max_length=160), validation: Literal['pending', 'passed', 'failed'] | None = None,
                cursor: str | None = Query(None, max_length=240), limit: int = Query(24, ge=1, le=100), db=Depends(get_db)):
    query = select(ModelPair).order_by(ModelPair.model_id, ModelPair.version)
    if validation:
        query = query.where(ModelPair.validation == validation)
    if cursor:
        try:
            model_id, version = cursor.split(':', 1)
        except ValueError:
            raise Error(422, 'invalid_cursor', '分页位置无效。')
        query = query.where(or_(ModelPair.model_id > model_id, (ModelPair.model_id == model_id) & (ModelPair.version > version)))
    items = []
    for pair in db.scalars(query):
        if q and q.casefold() not in (pair.definition['name'] + ' ' + pair.definition['template']['name']).casefold():
            continue
        items.append(service.dto(db, pair))
        if len(items) > limit:
            break
    last = items[limit-1] if len(items) > limit else None
    return ModelPage(items=items[:limit], next_cursor=f'{last.id}:{last.version}' if last else None)


@router.post('/models', response_model=ModelDTO, status_code=201)
def create_model(body: ModelInput, idempotency_key: str = Header(min_length=1, max_length=128), db=Depends(get_db), model_adapter=Depends(adapter)):
    return service.create(db, body, idempotency_key, model_adapter.data_origin)


@router.get('/models/{model_id}', response_model=ModelDTO)
def model_detail(model_id: str, version: str | None = None, db=Depends(get_db)):
    return service.dto(db, service.get(db, model_id, version))


@router.post('/models/{model_id}/versions', response_model=ModelDTO, status_code=201)
def new_version(model_id: str, body: ModelInput, idempotency_key: str = Header(min_length=1, max_length=128), db=Depends(get_db), model_adapter=Depends(adapter)):
    return service.create(db, body, idempotency_key, model_adapter.data_origin, model_id)


@router.post('/models/{model_id}/versions/{version}/verify', response_model=ModelDTO)
def verify(model_id: str, version: str, body: ModelVersionCommand, request: Request, db=Depends(get_db), model_adapter=Depends(adapter)):
    return service.verify(db, request.app.state.config, model_id, version, body.row_version, model_adapter)


async def public_references(request, model_id, version):
    # Call B's public HTTP contract, never its table/repository implementation.
    items, cursor = [], None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=request.app), base_url='http://workspace') as client:
        while True:
            response = await client.get('/api/v1/agent-services/references', params={'model_id': model_id, 'model_version': version, 'limit': 100, **({'cursor': cursor} if cursor else {})})
            if response.status_code != 200:
                raise Error(503, 'reference_service_unavailable', '智能体引用服务不可用，暂不能归档。', retryable=True)
            page = response.json(); items.extend(page['items'])
            next_cursor = page['next_cursor']
            if not next_cursor:
                return items
            if next_cursor == cursor:
                raise Error(502, 'provider_contract_invalid', '引用分页没有前进。')
            cursor = next_cursor


@router.post('/models/{model_id}/versions/{version}/archive', response_model=ModelDTO)
async def archive(model_id: str, version: str, body: ArchiveModel, request: Request, db=Depends(get_db)):
    service.lock(db)
    pair = service.get(db, model_id, version); service.check_version(pair, body.row_version)
    references = await public_references(request, model_id, version)
    blocked = [r for r in references if r['active_run_ids'] or (r['revision_state'] == 'published' and not r['runtime_checked'])]
    if blocked:
        raise Error(409, 'model_in_use', '模型正被活动运行引用，或无法确认已发布版本的运行状态。请先停止运行并恢复运行服务。', blocked)
    if references and not body.acknowledge_history:
        raise Error(409, 'model_history_confirmation', '该模型被历史配置引用，归档后不能新启动；历史快照保留，请确认影响。', references)
    pair.status = 'archived'; pair.row_version += 1; pair.updated_at = now(); db.flush()
    return service.dto(db, pair)


@router.get('/capabilities/models', response_model=CapabilityPage)
def capabilities(cursor: str | None = Query(None, max_length=240), limit: int = Query(100, ge=1, le=100), value=Depends(registry)):
    ordered = sorted(value.items, key=lambda i: (i.reference.model_id, i.reference.model_version))
    def key(i):
        return i.reference.model_id + ':' + i.reference.model_version
    if cursor:
        if cursor not in {key(i) for i in ordered}:
            raise Error(409, 'catalog_changed', '能力目录发生变化，请重新加载。')
        ordered = ordered[next(n for n, i in enumerate(ordered) if key(i) == cursor)+1:]
    return CapabilityPage(items=ordered[:limit], fingerprint=value.fingerprint, next_cursor=key(ordered[limit-1]) if len(ordered) > limit else None, data_origin=value.data_origin)


@router.get('/capabilities/models/{model_id}', response_model=CapabilityItem)
def capability(model_id: str, version: str | None = None, value=Depends(registry)):
    items = [i for i in value.items if i.reference.model_id == model_id and (not version or i.reference.model_version == version)]
    if not items:
        raise Error(404, 'model_not_available', '此模型版本未通过校验或已归档。')
    if len(items) != 1:
        raise Error(422, 'model_version_required', '该模型有多个可用版本，请指定 version。')
    return items[0]


@router.post('/capabilities/validate', response_model=CapabilityCheckResult)
def validate_capability(body: CapabilityCheck, value=Depends(registry)):
    issues = service.check_capability(value, body.capability_ref, body.target, body.rule)
    return CapabilityCheckResult(valid=not issues, unsupported_conditions=issues, fingerprint=value.fingerprint, data_origin=value.data_origin)


@router.get('/llm/deployments', response_model=DeploymentPage)
def deployments(db=Depends(get_db), model_adapter=Depends(adapter)):
    choices = service.selections(db); items = model_adapter.deployments()
    for item in items:
        item.selected_usages = [s.usage for s in choices if s.deployment_id == item.id]
    return DeploymentPage(items=items, selections=choices, data_origin=model_adapter.data_origin)


@router.put('/llm/selections/{usage}', response_model=Selection)
def select_deployment(usage: Usage, body: SelectDeployment, db=Depends(get_db), model_adapter=Depends(adapter)):
    if not any(d.id == body.deployment_id and usage in d.usages and d.health == 'healthy' for d in model_adapter.deployments()):
        raise Error(422, 'llm_not_healthy', '本地模型不存在、不健康或不支持该用途。')
    service.lock(db)
    row = db.get(LLMSelection, usage)
    if (row.row_version if row else 0) != body.row_version:
        raise Error(409, 'model_conflict', '用途选择已更新，请刷新后重试。')
    if row:
        row.deployment_id = body.deployment_id; row.row_version += 1
    else:
        row = LLMSelection(usage=usage, deployment_id=body.deployment_id); db.add(row)
    db.flush()
    return Selection.model_validate(row)


@router.post('/requirements/parse', response_model=ParseResult)
def parse(body: ParseInput, db=Depends(get_db), model_adapter=Depends(adapter)):
    deployment = service.selected(db, model_adapter, 'requirement_parse')
    result = ParseResult.model_validate(model_adapter.parse(body.requirement_text, deployment))
    if result.data_origin != model_adapter.data_origin or result.deployment_id != deployment.id or result.deployment_version != deployment.version:
        raise Error(502, 'provider_contract_invalid', '解析服务没有返回当前用途绑定的模型快照。')
    return result


@router.post('/requirements/evaluate', response_model=Assessment)
def evaluate(body: EvaluateInput, request: Request, db=Depends(get_db)):
    sources = []
    for channel in body.config.channels:
        for binding in channel_sources(channel):
            source = resolve_agent_source(db, binding.source_id)
            sources.append({k: getattr(source, k) for k in ('id', 'kind', 'width', 'height', 'duration_ms', 'status')})
    return request.app.state.agent_services.assess(body.config, sources, 'local-workspace')
