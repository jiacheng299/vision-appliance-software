"""路由状态机（S10–S14）：漂移定位、局部重路由、式(3) 滞回与版本切换。

这一层只改"路由版本"，不改报警规则：切换后新的观察窗口按新版本记录，
旧窗口保持它自己的版本，不会出现旧结果冒充新配置。
"""
import time

from sqlalchemy import select

from ...shared.errors import Error
from ...shared.models import now, uid
from ..agents.service import get_agent
from ..semantics import service as semantics
from . import capability as capabilities
from . import drift as drift_module
from . import graph as graphs
from . import hysteresis, solver
from .models import RouteDecision, RouteState
from .schemas import (DriftView, RouteDecisionView, RouteStateView, ScenarioView)

ACTIVE_FALLBACK = 'local-r{revision}'
ENTRY_KINDS = ('baseline', 'enter', 'switch', 'cancel', 'hold')


def _epoch():
    return time.time()


def state_of(row):
    return hysteresis.State(mode=row.mode, active_since=row.active_since,
                            candidate_since=row.candidate_since,
                            valid_windows=row.valid_windows,
                            hard_failure=bool(row.hard_failure))


def _apply(row, state):
    row.mode = state.mode
    row.active_since = state.active_since
    row.candidate_since = state.candidate_since
    row.valid_windows = state.valid_windows
    row.hard_failure = int(state.hard_failure)
    row.updated_at = now()


def _find(db, agent_id, actor_id, channel_id, source_id):
    return db.scalars(select(RouteState).where(RouteState.agent_id == agent_id,
                                               RouteState.actor_id == actor_id,
                                               RouteState.channel_id == channel_id,
                                               RouteState.source_id == source_id)).first()


def _ensure(db, agent_id, actor_id, channel_id, source_id, rule, baseline):
    row = _find(db, agent_id, actor_id, channel_id, source_id)
    if row is not None:
        return row, False
    row = RouteState(id=uid(), actor_id=actor_id, agent_id=agent_id, channel_id=channel_id,
                     source_id=source_id, rule=rule, active_members=list(baseline or []),
                     active_version='route-v1', active_since=_epoch(), mode=hysteresis.STABLE,
                     attribute_labels={})
    db.add(row)
    db.flush()
    return row, True


def _scenario(db, source_id, rule):
    profile = semantics.read_profile(db, source_id)
    from .service import _latest_evidence, _labels  # 复用同一套口径
    metrics, _evidence, _fell_back = _latest_evidence(db, source_id, f'person/{rule}')
    return capabilities.scenario_from(labels=_labels(profile.attributes),
                                      target_px=metrics.get('target_scale_px'),
                                      brightness=metrics.get('brightness'),
                                      blur=metrics.get('blur_score')), profile


def _current_evaluation(db, row, graph, scenario, weights, budgets, min_quality, table):
    members = tuple(row.active_members or ())
    if not members:
        return None
    combination = solver.Combination(id='current', label='当前组合', members=members)
    return solver.evaluate(combination, graph=graph, scenario=scenario, weights=weights,
                           budgets=budgets, table=table, min_quality=min_quality)


def _decision_row(db, row, *, kind, action, reason, delta_j=None, payload=None):
    entry = RouteDecision(id=uid(), route_state_id=row.id, agent_id=row.agent_id,
                          source_id=row.source_id, channel_id=row.channel_id, kind=kind,
                          action=action, reason=reason, delta_j=delta_j,
                          route_version=row.active_version, payload=payload or {},
                          created_at=now())
    db.add(entry)
    return entry


def _view(row, delta_j=None, drift_findings=(), report=None, chosen=None, notices=()):
    return RouteStateView(agent_id=row.agent_id, channel_id=row.channel_id,
                          source_id=row.source_id, rule=row.rule,
                          active_members=list(row.active_members or ()),
                          active_version=row.active_version, active_since=row.active_since,
                          mode=row.mode,
                          candidate_members=list(row.candidate_members or ()) or None,
                          candidate_score=row.candidate_score,
                          valid_windows=row.valid_windows,
                          hard_failure=bool(row.hard_failure),
                          delta_j=delta_j,
                          drift=[DriftView(attribute=item.attribute, kind=item.kind,
                                           previous=item.previous, current=item.current,
                                           reason=item.reason) for item in drift_findings],
                          affected=(report or {}).get('affected', []),
                          fixed=(report or {}).get('fixed', []),
                          escalated=bool((report or {}).get('escalated')),
                          escalation_reason=(report or {}).get('escalation_reason'),
                          chosen=_evaluation(chosen),
                          notices=list(notices),
                          updated_at=row.updated_at)


def _evaluation(item):
    if item is None:
        return None
    from .schemas import EvaluationView
    return EvaluationView(combination_id=item.combination.id, label=item.combination.label,
                          members=list(item.combination.members), score=item.score,
                          coverage=round(item.coverage, 6), dependency=item.dependency,
                          conflict=item.conflict, cost=round(item.cost, 6),
                          switch=round(item.switch, 6), feasible=item.feasible,
                          reasons=list(item.reasons), bucket=item.bucket)


def _thresholds():
    return hysteresis.Thresholds()


def list_states(db, agent_id, actor_id):
    get_agent(db, agent_id)
    rows = db.scalars(select(RouteState).where(RouteState.agent_id == agent_id,
                                               RouteState.actor_id == actor_id)
                      .order_by(RouteState.updated_at.desc())).all()
    return [_view(row) for row in rows]


def decisions(db, agent_id, actor_id, *, channel_id=None, source_id=None, limit=30):
    get_agent(db, agent_id)
    query = select(RouteDecision).where(RouteDecision.agent_id == agent_id)
    if channel_id:
        query = query.where(RouteDecision.channel_id == channel_id)
    if source_id:
        query = query.where(RouteDecision.source_id == source_id)
    rows = db.scalars(query.order_by(RouteDecision.sequence.desc()).limit(min(limit, 200))).all()
    return [RouteDecisionView(id=row.id, kind=row.kind, action=row.action, reason=row.reason,
                              delta_j=row.delta_j, route_version=row.route_version,
                              source_id=row.source_id, channel_id=row.channel_id,
                              created_at=row.created_at,
                              payload=row.payload or {}) for row in rows]


def active_route(db, agent_id, actor_id, channel_id, source_id, *, revision_no=None):
    """The route version a new window must be stamped with."""
    row = _find(db, agent_id, actor_id, channel_id, source_id)
    if row is None or not row.active_members:
        return (ACTIVE_FALLBACK.format(revision=revision_no if revision_no is not None else '0'),
                None)
    return row.active_version, tuple(row.active_members)


def propose(db, agent_id, actor_id, *, channel_id, source_id, rule, duration_seconds=None,
            table=None, weights=None, budgets=None, min_quality=solver.MIN_QUALITY,
            revision_no=None):
    """Detect drift, re-route only the affected subgraph, then run one hysteresis step."""
    get_agent(db, agent_id)
    table = table or capabilities.table()
    try:
        graph = graphs.build(rule, duration_seconds=duration_seconds)
    except graphs.GraphError as error:
        raise Error(422, 'route_rule_invalid', str(error)) from None
    scenario, profile = _scenario(db, source_id, rule)
    baseline_solution = solver.solve(graph=graph, scenario=scenario, table=table,
                                     weights=weights, budgets=budgets, min_quality=min_quality)
    baseline = (baseline_solution.chosen.combination.members
                if baseline_solution.chosen else ())
    row, first_time = _ensure(db, agent_id, actor_id, channel_id, source_id, rule,
                              baseline=baseline)
    findings = drift_module.detect(profile.attributes,
                                   previous_labels=row.attribute_labels or {},
                                   cursor=row.drift_cursor)
    row.attribute_labels = {**drift_module.labels_of(profile.attributes)}
    row.drift_cursor = drift_module.cursor_of(profile.attributes, row.drift_cursor)

    solution, report = solver.solve_local(graph=graph, scenario=scenario,
                                          drifted_keys=drift_module.drifted_keys(findings),
                                          current_members=tuple(row.active_members or ()),
                                          table=table, weights=weights, budgets=budgets,
                                          min_quality=min_quality)
    current = _current_evaluation(db, row, graph, scenario, weights, budgets, min_quality, table)
    hard_failure = current is not None and not current.feasible
    delta = None
    if current is not None and current.feasible and solution.chosen is not None:
        delta = solution.chosen.score - current.score
    if solution.chosen is None:
        # 没有安全替代时不做任何改动：保持原组合并让观察记录输出观察不足。
        decision = hysteresis.Decision(
            hysteresis.HOLD, state_of(row),
            '没有可行组合：当前组合失效时保持原状，观察记录输出观察不足')
        kind = 'blocked'
    else:
        decision = hysteresis.decide(
            state=state_of(row), delta_j=delta, now=_epoch(),
            elapsed=(_epoch() - row.active_since) if row.active_since else None,
            thresholds=_thresholds(), hard_infeasible=hard_failure)
        kind = ('drift' if drift_module.drifted_keys(findings)
                else 'expiry' if drift_module.expired_keys(findings)
                else 'baseline' if first_time else 'refresh')
    _apply(row, decision.state)
    if row.mode == hysteresis.CANDIDATE and solution.chosen is not None:
        row.candidate_members = list(solution.chosen.combination.members)
        row.candidate_score = solution.chosen.score
        if row.candidate_since is None:
            row.candidate_since = _epoch()
    elif row.mode != hysteresis.CANDIDATE:
        # Candidate fields only exist while a candidate is actually being verified.
        row.candidate_members = None
        row.candidate_score = None
        row.candidate_since = None
    _decision_row(db, row, kind=kind, action=decision.action, reason=decision.reason,
                  delta_j=delta,
                  payload={'drift': [item.__dict__ for item in findings],
                           'affected': report.get('affected', []),
                           'fixed': report.get('fixed', []),
                           'escalated': report.get('escalated'),
                           'candidate': list(solution.chosen.combination.members) if solution.chosen else None})
    db.flush()
    notices = []
    if drift_module.expired_keys(findings):
        notices.append('以下属性只是过期，系统将补充抽帧而不是认定场景反向变化：'
                       + '、'.join(drift_module.expired_keys(findings)))
    if drift_module.drifted_keys(findings) and report.get('escalated'):
        notices.append('无法局部修复，已退化为全图重算：' + str(report.get('escalation_reason')))
    return _view(row, delta_j=delta, drift_findings=findings, report=report,
                 chosen=solution.chosen, notices=notices)


def cancel_candidate(db, agent_id, actor_id, *, channel_id, source_id):
    row = _find(db, agent_id, actor_id, channel_id, source_id)
    if row is None:
        raise Error(404, 'route_state_missing', '该视频源还没有路由状态。')
    state = state_of(row)
    if state.mode != hysteresis.CANDIDATE:
        raise Error(409, 'route_no_candidate', '当前没有待验证的候选组合。')
    _apply(row, hysteresis.State(mode=hysteresis.STABLE, active_since=state.active_since))
    row.candidate_members = None
    row.candidate_score = None
    row.candidate_since = None
    _decision_row(db, row, kind='cancel', action=hysteresis.CANCEL, reason='人工取消候选组合')
    db.flush()
    return _view(row)


def advance_window(db, agent_id, actor_id, *, channel_id, source_id, rule, verdict,
                   duration_seconds=None, table=None, weights=None, budgets=None,
                   min_quality=solver.MIN_QUALITY):
    """Feed one closed observation window into the routing state machine."""
    row = _find(db, agent_id, actor_id, channel_id, source_id)
    if row is None:
        return None
    graph = graphs.build(rule, duration_seconds=duration_seconds)
    scenario, _ = _scenario(db, source_id, rule)
    solution, report = solver.solve_local(graph=graph, scenario=scenario, drifted_keys=(),
                                          current_members=tuple(row.active_members or ()),
                                          table=table, weights=weights, budgets=budgets,
                                          min_quality=min_quality)
    current = _current_evaluation(db, row, graph, scenario, weights, budgets, min_quality, table)
    hard_failure = current is not None and not current.feasible
    delta = None
    if current is not None and current.feasible and solution.chosen is not None:
        delta = solution.chosen.score - current.score
    decision = hysteresis.decide(state=state_of(row), delta_j=delta, now=_epoch(),
                                 thresholds=_thresholds(), hard_infeasible=hard_failure,
                                 window_valid=verdict != 'insufficient')
    previous_version = row.active_version
    _apply(row, decision.state)
    if decision.action == hysteresis.SWITCH and row.candidate_members:
        row.active_members = list(row.candidate_members)
        row.active_version = _next_version(previous_version)
        row.active_since = _epoch()
        row.candidate_members = None
        row.candidate_score = None
        row.candidate_since = None
        row.valid_windows = 0
    _decision_row(db, row, kind='window', action=decision.action, reason=decision.reason,
                  delta_j=delta, payload={'verdict': verdict,
                                          'affected': report.get('affected', [])})
    db.flush()
    return _view(row, delta_j=delta, report=report, chosen=solution.chosen)


def _next_version(version):
    try:
        number = int(str(version).rsplit('v', 1)[1])
    except (IndexError, ValueError):
        number = 1
    return f'route-v{number + 1}'


def timeline(db, agent_id, actor_id, *, channel_id, source_id, limit=40):
    """Merge profile version bumps and routing decisions into one ordered axis."""
    from ..semantics.service import list_events
    from .schemas import TimelineEntryView
    limit = min(max(limit, 1), 200)
    entries = []
    for event in list_events(db, source_id, limit=limit):
        entries.append(TimelineEntryView(
            id=event.id, at=event.created_at, origin='profile', kind=event.kind,
            version=f'v{event.version}', summary=event.summary, attribute=event.attribute,
            previous=event.previous, current=event.current))
    rows = db.scalars(select(RouteDecision)
                      .where(RouteDecision.agent_id == agent_id,
                             RouteDecision.channel_id == channel_id,
                             RouteDecision.source_id == source_id)
                      .order_by(RouteDecision.sequence.desc()).limit(limit)).all()
    for row in rows:
        entries.append(TimelineEntryView(
            id=row.id, at=row.created_at, origin='route', kind=row.kind,
            version=row.route_version or '—', summary=row.reason, action=row.action,
            delta_j=row.delta_j))
    entries.sort(key=lambda item: item.at, reverse=True)
    return entries[:limit]