"""把画像现状、需求图与能力表合成一次路由评估（S3–S4）。

这里只做评估，不改任务配置：真正的组合发布与切换在后续阶段接入。
"""
from ...shared.errors import Error
from .. import sources as sources_module
from ..semantics import service as semantics
from . import capability as capabilities
from . import graph as graphs
from . import solver
from .schemas import (CapabilityView, EdgeView, EvaluationView, EvidenceView, RequirementView,
                      RouteView, ScenarioView)


def _labels(attributes):
    labels = []
    for attribute in attributes:
        if not attribute.usable:
            continue
        value = attribute.value or {}
        label = value.get('label') if isinstance(value, dict) else None
        if isinstance(label, str):
            labels.append(label)
    return labels


VALID_VERDICTS = ('detected', 'not_detected')


def _latest_evidence(db, source_id, task_key):
    """场景证据优先取最近一次**有效**观察；没有时才退回最近一条并标记为未证实。

    直接取"最后一条"会把一次没看清的窗口当成既成事实；而退回默认分桶又会
    悄悄抬高评分（默认分桶的质量高于眩光等分桶），所以这里只做"换一条更可信的
    证据 + 标注"，不改动求解规则。
    """
    from ..semantics.models import ObservationRecord
    from sqlalchemy import select
    base = select(ObservationRecord).where(ObservationRecord.source_id == source_id,
                                           ObservationRecord.task_key == task_key)
    valid = db.scalars(base.where(ObservationRecord.verdict.in_(VALID_VERDICTS))
                       .order_by(ObservationRecord.sequence.desc()).limit(1)).first()
    if valid is not None:
        return dict(valid.metrics), valid, False
    fallback = db.scalars(base.order_by(ObservationRecord.sequence.desc()).limit(1)).first()
    if fallback is None:
        return {}, None, False
    return dict(fallback.metrics), fallback, True


def _capability_views(table):
    views = []
    for capability in table.values():
        views.append(CapabilityView(id=capability.id, label=capability.label,
                                    kind=capability.kind, target=capability.target,
                                    installed=capability.installed,
                                    calibrated=capability.calibrated,
                                    provides=list(capability.provides),
                                    quality={key: float(value) for key, value in capability.quality.items()},
                                    bucket_quality={bucket: {key: float(value) for key, value in column.items()}
                                                    for bucket, column in capability.quality_by_bucket.items()},
                                    cpu_ms=capability.cpu_ms, memory_mb=capability.memory_mb,
                                    limitations=list(capability.limitations)))
    return views


def _evaluation_view(item):
    return EvaluationView(combination_id=item.combination.id, label=item.combination.label,
                          members=list(item.combination.members), score=item.score,
                          coverage=round(item.coverage, 6), dependency=item.dependency,
                          conflict=item.conflict, cost=round(item.cost, 6),
                          switch=round(item.switch, 6), feasible=item.feasible,
                          reasons=list(item.reasons), bucket=item.bucket)


def _notices(table, scenario, metrics, evidence=None, fell_back=False):
    notices = []
    uncalibrated = [capability.label for capability in table.values() if not capability.calibrated]
    if uncalibrated:
        notices.append('以下能力的质量数字是保守示例值，未做分桶验证，不能当作准确率：'
                       + '、'.join(uncalibrated))
    if not metrics:
        notices.append('该视频源还没有观察记录，目标尺度按未测定处理。')
    elif fell_back:
        notices.append('该视频源还没有有效观察窗口；最近一次是"观察不足"，'
                       '它给出的目标尺度与画质只能作为提示，不能当作已成立的场景条件。')
    if scenario.saturated_ratio is None:
        notices.append('不可恢复饱和像素比例未测定，去眩光类预处理能否修复当前画面无法确认。')
    if scenario.bucket != capabilities.DEFAULT_BUCKET:
        notices.append(f'当前按场景分桶 {scenario.bucket} 读取质量列。')
    return notices


def evaluate_route(db, source_id, rule, *, duration_seconds=None, table=None,
                   weights=None, budgets=None, min_quality=solver.MIN_QUALITY):
    sources_module.get_source(db, source_id)
    table = table or capabilities.table()
    try:
        requirement_graph = graphs.build(rule, duration_seconds=duration_seconds)
    except graphs.GraphError as error:
        raise Error(422, 'route_rule_invalid', str(error)) from None
    profile = semantics.read_profile(db, source_id)
    metrics, evidence, fell_back = _latest_evidence(db, source_id, f'person/{rule}')
    scenario = capabilities.scenario_from(labels=_labels(profile.attributes),
                                          target_px=metrics.get('target_scale_px'),
                                          brightness=metrics.get('brightness'),
                                          blur=metrics.get('blur_score'))
    current_members = profile.runtime.get('route_members')
    current = (solver.Combination(id='current', label='当前组合',
                                  members=tuple(current_members))
               if current_members else None)
    solution = solver.solve(graph=requirement_graph, scenario=scenario, table=table,
                            weights=weights, budgets=budgets, current=current,
                            min_quality=min_quality)
    return RouteView(source_id=source_id, rule=rule, profile_version=profile.version,
                     scenario=ScenarioView(bucket=scenario.bucket,
                                           saturated_ratio=scenario.saturated_ratio,
                                           target_px=scenario.target_px,
                                           brightness=scenario.brightness,
                                           blur=scenario.blur,
                                           reasons=list(scenario.reasons)),
                     graph={'requirements': [RequirementView(key=item.key, kind=item.kind,
                                                             target=item.target,
                                                             weight=item.weight,
                                                             description=item.description)
                                             for item in requirement_graph.requirements],
                            'edges': [EdgeView(source=edge.source, target=edge.target,
                                               kind=edge.kind, seconds=edge.seconds)
                                      for edge in requirement_graph.dependencies()]},
                     capabilities=_capability_views(table),
                     chosen=_evaluation_view(solution.chosen) if solution.chosen else None,
                     ranked=[_evaluation_view(item) for item in solution.ranked],
                     blocked=[_evaluation_view(item) for item in solution.blocked],
                     weights=solution.weights.as_dict(), budgets=solution.budgets.as_dict(),
                     min_quality=min_quality,
                     evidence=_evidence_view(evidence),
                     notices=_notices(table, scenario, metrics, evidence, fell_back))


def _evidence_view(row):
    """哪一条观察记录在为本次路由提供场景证据。"""
    if row is None:
        return None
    return EvidenceView(observation_id=row.id, verdict=row.verdict,
                        window_start=row.window_start, window_end=row.window_end,
                        usable=row.verdict != 'insufficient',
                        confidence='confirmed' if row.verdict != 'insufficient' else 'unverified')
