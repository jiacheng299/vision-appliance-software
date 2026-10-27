"""Two task modes; natural language selects a proven template before VLM execution.

A multimodal plan is a server-issued immutable execution recipe, not a fabricated
small-model/template reference. B persists it verbatim and the runtime consumes it.
"""
from datetime import datetime, timedelta, timezone
from ...shared.errors import Error
from ...shared.models import now, uid
from ..agents.schemas import ChannelConfig, ExecutionPlanRef, channel_sources
from .models import RequirementPlan
from .schemas import FixedTaskTemplate, PlanResult, TemplateMatch, MultimodalAnalysis
from . import service

NAMES = {('fire', 'presence'): '检测火源', ('person', 'intrusion'): '检测是否有人进入区域',
         ('person', 'dwell'): '人员区域停留检测', ('person', 'absence'): '人员离岗检测'}


def templates(catalog):
    result = []
    for item in catalog.items:
        for target in item.targets:
            for rule in item.rules:
                result.append(FixedTaskTemplate(id=service.digest([item.reference.model_dump(), target, rule]),
                    name=NAMES.get((target, rule), f'{item.name} / {target} / {rule}'), target=target, rule=rule,
                    capability_ref=item.reference, requires_region=rule in item.requires_region,
                    requires_duration=rule in item.requires_duration, limitations=item.limitations))
    return result


def binding_issues(channel, needs_region, needs_duration):
    missing = []
    if not channel_sources(channel):
        missing.append('请选择至少一个视频源。')
    if needs_duration and channel.duration_seconds is None:
        missing.append('请明确持续时长，不能从“太久”自动推断。')
    for binding in channel_sources(channel):
        if needs_region and not binding.regions:
            missing.append(f'{binding.source_id}：请绘制此视频的监测区域。')
    return missing


def generate(db, channel, catalog, adapter, sources):
    if channel.task_mode != 'natural_language' or not channel.requirement_text.strip():
        raise Error(422, 'task_mode_invalid', '自然语言任务需要填写完整需求，再生成执行方案。')
    resolved = channel.model_copy(deep=True)
    resolved.execution_plan = None
    resolved.capability_ref = None
    # Matching must prove full coverage, never just extract a convenient keyword.
    match = adapter.match_template(resolved.requirement_text, catalog) if catalog.items else None
    item = None
    if match is not None:
        match = TemplateMatch.model_validate(match)
        if match.covers_all_requirements:
            item = next((i for i in catalog.items if i.reference == match.capability_ref and match.target in i.targets and match.rule in i.rules), None)
            if item is None:
                raise Error(502, 'provider_contract_invalid', '模板匹配服务返回了不可用的模板引用。')
    identifier = uid()
    if item is not None:
        strategy = 'template'
        resolved.target, resolved.rule, resolved.capability_ref = match.target, match.rule, item.reference
        if match.duration_seconds is not None:
            resolved.duration_seconds = match.duration_seconds
        reason = '原始需求完整匹配已有模板，优先由模板绑定的小模型执行。'
        limits = item.limitations
        plan = ExecutionPlanRef(plan_id=identifier, executor_kind=strategy, reason=reason, limitations=limits,
            requires_region=resolved.rule in item.requires_region, requires_duration=resolved.rule in item.requires_duration)
        missing = binding_issues(resolved, plan.requires_region, plan.requires_duration)
        verdict = 'clarification_required' if missing else 'executable'
    else:
        strategy = 'multimodal'
        deployment = service.selected(db, adapter, 'multimodal_analysis')
        analysis = MultimodalAnalysis.model_validate(adapter.analyze_multimodal(resolved, sources, deployment))
        # Preserve the full original request as the runtime instruction.
        if analysis.instruction != resolved.requirement_text:
            raise Error(502, 'provider_contract_invalid', '多模态方案必须保留完整原始需求，不能静默删减条件。')
        resolved.target, resolved.rule = analysis.target, analysis.rule
        if analysis.duration_seconds is not None:
            resolved.duration_seconds = analysis.duration_seconds
        reason = '已有模板无法完整覆盖需求，使用多模态大模型分析并执行该任务。'
        limits = analysis.limitations
        plan = ExecutionPlanRef(plan_id=identifier, executor_kind=strategy, deployment_id=deployment.id,
            deployment_version=deployment.version, instruction=analysis.instruction, reason=reason, limitations=limits,
            requires_region=analysis.requires_region, requires_duration=analysis.requires_duration)
        missing = list(dict.fromkeys(analysis.missing_conditions + binding_issues(resolved, plan.requires_region, plan.requires_duration)))
        verdict = analysis.verdict
        if verdict == 'executable' and missing:
            verdict = 'clarification_required'
    if channel.duration_seconds is not None and resolved.duration_seconds is not None and channel.duration_seconds != resolved.duration_seconds:
        resolved.duration_seconds = channel.duration_seconds
        missing.append('自然语言中的时长与补充条件不一致，请统一后重新生成方案。')
        if verdict == 'executable':
            verdict = 'clarification_required'
    resolved.execution_plan = plan
    expires = (datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat().replace('+00:00', 'Z')
    # No write lock is retained during an external model response.
    db.rollback()
    db.add(RequirementPlan(id=identifier, resolved_channel=resolved.model_dump(mode='json'),
        catalog_fingerprint=catalog.fingerprint, verdict=verdict, missing_conditions=missing,
        limitations=limits, data_origin=adapter.data_origin, expires_at=expires))
    db.flush()
    return PlanResult(id=identifier, strategy=strategy, channel=resolved, verdict=verdict,
        missing_conditions=missing, reason=reason, limitations=limits, expires_at=expires, data_origin=adapter.data_origin)


def verify(db, channel, catalog, adapter):
    plan = channel.execution_plan
    row = db.get(RequirementPlan, plan.plan_id) if plan else None
    if (not row or row.data_origin != adapter.data_origin or row.expires_at <= now()
            or row.catalog_fingerprint != catalog.fingerprint
            or service.digest(row.resolved_channel) != service.digest(channel.model_dump(mode='json'))):
        raise Error(409, 'execution_plan_stale', '需求、条件或能力发生变化，或方案已过期，请重新生成执行方案。')
    if plan.executor_kind == 'multimodal':
        if not any(d.id == plan.deployment_id and d.version == plan.deployment_version and d.health == 'healthy'
                   and 'multimodal_analysis' in d.usages for d in adapter.deployments()):
            raise Error(503, 'multimodal_service_unavailable', '方案引用的多模态大模型版本当前不可用。', retryable=True)
    return row
