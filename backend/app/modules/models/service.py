import hashlib
import json
from sqlalchemy import select, text
from ...shared.errors import Error
from ...shared.models import uid, now
from ..agents.contracts import CapabilityCatalog, CapabilityItem, Assessment
from ..agents.schemas import CapabilityRef, channel_sources
from .models import ModelFile, ModelPair, ModelCommand, LLMSelection
from .schemas import ModelDTO, ModelInput, Selection


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def lock(db):
    db.rollback()
    db.execute(text('BEGIN IMMEDIATE'))


def dto(db, pair):
    file = db.get(ModelFile, pair.file_id)
    return ModelDTO(**pair.definition, id=pair.model_id, template_id=pair.template_id, checksum=file.checksum,
        size_bytes=file.size_bytes, validation=pair.validation, validation_message=pair.validation_message,
        status=pair.status, row_version=pair.row_version, data_origin=pair.data_origin,
        created_at=pair.created_at, updated_at=pair.updated_at)


def get(db, identifier, version=None):
    query = select(ModelPair).where(ModelPair.model_id == identifier)
    if version is not None:
        query = query.where(ModelPair.version == version)
    pair = db.scalar(query.order_by(ModelPair.created_at.desc(), ModelPair.version.desc()))
    if not pair:
        raise Error(404, 'model_not_found', '模型版本不存在。')
    return pair


def check_version(pair, version):
    if pair.row_version != version:
        raise Error(409, 'model_conflict', '模型状态已更新，请刷新后重试。')


def create(db, body, key, origin, model_id=None):
    payload = [model_id, body.model_dump(mode='json')]
    lock(db)
    previous = db.get(ModelCommand, key)
    if previous:
        if previous.request_hash != digest(payload):
            raise Error(409, 'idempotency_conflict', '同一请求编号已用于不同内容。')
        return ModelDTO.model_validate(previous.response)
    if not db.get(ModelFile, body.file_id):
        raise Error(422, 'model_file_required', '请先上传完整的本地模型文件。')
    identifier, template_id = model_id or uid(), uid()
    if model_id:
        old = get(db, model_id)
        template_id = old.template_id
        if db.get(ModelPair, (model_id, body.version)) or db.scalar(select(ModelPair).where(ModelPair.template_id == template_id, ModelPair.template_version == body.template.version)):
            raise Error(409, 'model_version_exists', '模型和模板均须使用新的版本号，不能覆盖已有版本。')
    pair = ModelPair(model_id=identifier, version=body.version, template_id=template_id,
        template_version=body.template.version, file_id=body.file_id, definition=body.model_dump(mode='json'), data_origin=origin)
    db.add(pair); db.flush()
    result = dto(db, pair)
    db.add(ModelCommand(key=key, request_hash=digest(payload), response=result.model_dump(mode='json')))
    return result


def file_hash(path):
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify(db, config, identifier, version, expected, adapter):
    pair = get(db, identifier, version); check_version(pair, expected)
    if pair.status == 'archived':
        raise Error(409, 'model_archived', '已归档版本不能重新开放，请创建新版本。')
    definition, file = ModelInput.model_validate(pair.definition), db.get(ModelFile, pair.file_id)
    path = config.var_root / 'model-files' / file.id
    checksum = file.checksum
    db.rollback()
    if not path.is_file() or path.stat().st_size != file.size_bytes or file_hash(path) != checksum:
        state, message = 'failed', '本地文件缺失或 SHA-256 不一致，请重新导入新版本。'
    else:
        try:
            state, message = adapter.verify(definition, path, checksum)
            if state not in ('passed', 'failed'):
                raise Error(502, 'provider_contract_invalid', '算法校验适配器返回了无效状态。')
        except Error as exc:
            if exc.status != 503:
                raise
            state, message = 'pending', exc.message
    lock(db)
    pair = get(db, identifier, version); check_version(pair, expected)
    pair.validation, pair.validation_message = state, message
    pair.row_version += 1; pair.updated_at = now()
    db.flush()
    return dto(db, pair)


def catalog(db, origin):
    pairs = db.scalars(select(ModelPair).where(ModelPair.validation == 'passed', ModelPair.status == 'available', ModelPair.data_origin == origin).order_by(ModelPair.model_id, ModelPair.version)).all()
    items = []
    for pair in pairs:
        definition = ModelInput.model_validate(pair.definition)
        t = definition.template
        items.append(CapabilityItem(name=f'{definition.name} + {t.name}', reference=CapabilityRef(model_id=pair.model_id, model_version=pair.version,
            template_id=pair.template_id, template_version=pair.template_version), targets=t.targets, rules=t.rules,
            requires_region=t.requires_region, requires_duration=t.requires_duration, limitations=t.limitations))
    return CapabilityCatalog(items=items, fingerprint=digest([[p.model_id, p.version, p.template_version, p.file_id, p.row_version, p.definition] for p in pairs]), data_origin=origin)


def check_capability(catalog, ref, target, rule):
    item = next((i for i in catalog.items if i.reference == ref), None)
    if not item:
        return ['模型/模板引用不在当前可用能力目录中，请检查版本与校验状态。']
    return ([] if target in item.targets else [f'模型未声明支持目标：{target or "未指定"}。']) + ([] if rule in item.rules else [f'模板未声明支持规则：{rule or "未指定"}。'])


def deterministic_assessment(config, sources, catalog):
    missing, unsupported, chosen = [], [], []
    if not config.channels:
        missing.append('请至少添加一个通道。')
    for channel in config.channels:
        prefix = channel.name + '：'
        if not channel.requirement_text:
            missing.append(prefix + '请填写原始需求。')
        if not channel_sources(channel):
            missing.append(prefix + '请选择视频源。')
        if not channel.capability_ref:
            missing.append(prefix + '请选择经过校验的模型与模板。'); continue
        errors = check_capability(catalog, channel.capability_ref, channel.target, channel.rule)
        unsupported.extend(prefix + v for v in errors)
        if errors:
            continue
        item = next(i for i in catalog.items if i.reference == channel.capability_ref)
        chosen.append(item.reference)
        if channel.rule in item.requires_duration and channel.duration_seconds is None:
            missing.append(prefix + '请明确持续时长。')
        for binding in channel_sources(channel):
            source = next((s for s in sources if s['id'] == binding.source_id), None)
            if not source:
                unsupported.append(prefix + '视频源不可用。'); continue
            if channel.rule in item.requires_region and not binding.regions:
                missing.append(prefix + f'{binding.source_id} 尚未绘制区域。')
            if binding.start_media_ms is not None and (source['kind'] != 'file' or source.get('duration_ms') is None or binding.end_media_ms > source['duration_ms']):
                unsupported.append(prefix + '录像区间超出视频时长，或摄像头不支持录像区间。')
            if catalog.data_origin == 'real' and source.get('status') not in (None, 'ready', 'online'):
                unsupported.append(prefix + '视频源尚未就绪。')
    return Assessment(verdict='unsupported' if unsupported else 'clarification_required' if missing else 'executable', missing_conditions=missing,
        unsupported_conditions=unsupported, chosen_capabilities=chosen, capability_fingerprint=catalog.fingerprint, data_origin=catalog.data_origin)


def selections(db):
    return [Selection(usage=u, deployment_id=(r.deployment_id if (r := db.get(LLMSelection, u)) else None), row_version=r.row_version if r else 0)
            for u in ('requirement_parse', 'multimodal_analysis')]


def selected(db, adapter, usage):
    row = db.get(LLMSelection, usage)
    deployment = next((d for d in adapter.deployments() if row and d.id == row.deployment_id and usage in d.usages and d.health == 'healthy'), None)
    if not deployment:
        raise Error(503, 'llm_not_selected', '该用途尚未绑定健康的本地模型，请在模型管理中选择；没有部署服务时可保存草稿。', retryable=True)
    return deployment
