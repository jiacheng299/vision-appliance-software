"""漂移、滞回与局部重路由：过期不等于反向变化，抖动不等于该等。"""
from types import SimpleNamespace

import pytest

from app.modules.routing import capability as capabilities, drift, graph as graphs, hysteresis, solver


def attribute(key, label, *, observed_at=100.0, usable=True, state='valid'):
    return SimpleNamespace(key=key, value={'label': label} if label is not None else {},
                           observed_at=observed_at, usable=usable, state=state,
                           confidence=0.8, strength=0.8 if usable else 0.0, reason=None)


# --- 漂移 ---

def test_first_observation_is_a_baseline_not_a_drift():
    findings = drift.detect([attribute('lighting', 'daylight')])
    assert [finding.kind for finding in findings] == [drift.BASELINE]
    assert drift.drifted_keys(findings) == ()


def test_new_evidence_with_a_different_label_confirms_drift():
    findings = drift.detect([attribute('lighting', 'strong_glare', observed_at=200.0)],
                            previous_labels={'lighting': 'daylight'}, cursor=150.0)
    assert [finding.kind for finding in findings] == [drift.CONFIRMED]
    assert findings[0].previous == 'daylight' and findings[0].current == 'strong_glare'
    assert drift.drifted_keys(findings) == ('lighting',)


def test_evidence_older_than_the_cursor_carries_no_news():
    findings = drift.detect([attribute('lighting', 'strong_glare', observed_at=100.0)],
                            previous_labels={'lighting': 'daylight'}, cursor=150.0)
    assert findings == ()


def test_same_label_is_not_drift_even_when_the_frame_is_new():
    findings = drift.detect([attribute('lighting', 'daylight', observed_at=300.0)],
                            previous_labels={'lighting': 'daylight'}, cursor=150.0)
    assert findings == ()


def test_expiry_is_reported_as_needing_new_frames_not_as_a_reversed_scene():
    findings = drift.detect([attribute('lighting', None, usable=False, state='expired')],
                            previous_labels={'lighting': 'daylight'}, cursor=150.0)
    assert [finding.kind for finding in findings] == [drift.EXPIRED]
    assert drift.drifted_keys(findings) == ()
    assert drift.expired_keys(findings) == ('lighting',)
    assert '不认定场景反向变化' in findings[0].reason


def test_labels_and_cursor_track_only_usable_evidence():
    attributes = [attribute('lighting', 'daylight', observed_at=10.0),
                  attribute('weather', 'snow', observed_at=40.0),
                  attribute('occlusion', None, observed_at=90.0, usable=False)]
    assert drift.labels_of(attributes) == {'lighting': 'daylight', 'weather': 'snow'}
    assert drift.cursor_of(attributes) == 40.0
    assert drift.cursor_of(attributes, previous=80.0) == 80.0


# --- 式(3) 滞回 ---

def test_entry_needs_both_the_gain_threshold_and_the_dwell_time():
    stable = hysteresis.State(mode=hysteresis.STABLE, active_since=0.0)
    early = hysteresis.decide(state=stable, delta_j=0.5, now=30.0, elapsed=30.0)
    assert early.action == hysteresis.HOLD and '最短驻留' in early.reason
    ready = hysteresis.decide(state=stable, delta_j=0.5, now=200.0, elapsed=200.0)
    assert ready.action == hysteresis.ENTER and ready.state.mode == hysteresis.CANDIDATE
    assert ready.state.valid_windows == 0


def test_gain_below_the_entry_threshold_never_enters():
    stable = hysteresis.State(mode=hysteresis.STABLE)
    decision = hysteresis.decide(state=stable, delta_j=0.01, now=200.0, elapsed=200.0)
    assert decision.action == hysteresis.HOLD


def test_gain_summaries_use_business_language_without_formula_symbols():
    stable = hysteresis.State(mode=hysteresis.STABLE)
    entered = hysteresis.decide(state=stable, delta_j=0.5, now=200.0, elapsed=200.0)
    held = hysteresis.decide(state=stable, delta_j=0.01, now=200.0, elapsed=200.0)
    candidate = hysteresis.State(mode=hysteresis.CANDIDATE, candidate_since=10.0, valid_windows=1)
    cancelled = hysteresis.decide(state=candidate, delta_j=-0.2, now=20.0, window_valid=True)

    assert entered.reason == '评分增益达到进入阈值（当前评分增益 0.500 ≥ 进入阈值 0.060）'
    assert held.reason == '评分增益未达到进入阈值（当前评分增益 0.010）'
    assert cancelled.reason == '评分增益回落到取消阈值以下（当前评分增益 -0.200 ≤ 取消阈值 −0.060）'
    assert all('ΔJ' not in decision.reason for decision in (entered, held, cancelled))


def test_a_falling_gain_cancels_the_candidate():
    candidate = hysteresis.State(mode=hysteresis.CANDIDATE, candidate_since=10.0, valid_windows=1)
    decision = hysteresis.decide(state=candidate, delta_j=-0.2, now=20.0, window_valid=True)
    assert decision.action == hysteresis.CANCEL
    assert decision.state.mode == hysteresis.STABLE
    assert decision.state.valid_windows == 0


def test_switching_requires_the_configured_number_of_valid_windows():
    thresholds = hysteresis.Thresholds(required_windows=2)
    candidate = hysteresis.State(mode=hysteresis.CANDIDATE, candidate_since=10.0, valid_windows=0)
    first = hysteresis.decide(state=candidate, delta_j=0.2, now=20.0, window_valid=True,
                              thresholds=thresholds)
    assert first.action == hysteresis.HOLD and first.state.valid_windows == 1
    second = hysteresis.decide(state=first.state, delta_j=0.2, now=40.0, window_valid=True,
                               thresholds=thresholds)
    assert second.action == hysteresis.SWITCH and second.state.mode == hysteresis.STABLE


def test_an_invalid_window_does_not_count_towards_the_switch():
    thresholds = hysteresis.Thresholds(required_windows=2)
    candidate = hysteresis.State(mode=hysteresis.CANDIDATE, candidate_since=10.0, valid_windows=1)
    decision = hysteresis.decide(state=candidate, delta_j=0.2, now=40.0, window_valid=False,
                                 thresholds=thresholds)
    assert decision.action == hysteresis.HOLD and decision.state.valid_windows == 1


def test_a_hard_failure_bypasses_the_gain_wait_but_still_waits_one_window():
    stable = hysteresis.State(mode=hysteresis.STABLE, active_since=0.0)
    entered = hysteresis.decide(state=stable, delta_j=None, now=5.0, elapsed=5.0,
                                hard_infeasible=True, window_valid=True)
    assert entered.action == hysteresis.ENTER and entered.state.hard_failure is True
    assert entered.state.valid_windows == 1
    switched = hysteresis.decide(state=entered.state, delta_j=None, now=40.0, window_valid=True)
    assert switched.action == hysteresis.SWITCH


def test_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        hysteresis.decide(state=hysteresis.State(mode='weird'), delta_j=0.1, now=1.0)


# --- 局部重路由 ---

CURRENT = ('yolo11n-person', 'heuristic-tracker', 'zone-rule')


def test_lighting_drift_only_reroutes_the_detector():
    solution, report = solver.solve_local(graph=graphs.build('intrusion'),
                                          scenario=capabilities.Scenario(),
                                          drifted_keys=('lighting',),
                                          current_members=CURRENT)
    assert report['affected'] == ['person_detect']
    assert report['fixed'] == ['person_track', 'zone_intersect']
    assert report['escalated'] is False
    assert solution.chosen is not None
    assert {'heuristic-tracker', 'zone-rule'} <= set(solution.chosen.combination.members)
    assert solution.chosen.switch == 0.0


def test_occlusion_drift_widens_to_detection_and_tracking_but_keeps_the_zone_rule():
    solution, report = solver.solve_local(graph=graphs.build('intrusion'),
                                          scenario=capabilities.Scenario(),
                                          drifted_keys=('occlusion',),
                                          current_members=CURRENT)
    assert report['affected'] == ['person_detect', 'person_track']
    assert report['fixed'] == ['zone_intersect']
    assert 'zone-rule' in solution.chosen.combination.members


def test_a_single_requirement_graph_escalates_to_a_full_solve():
    solution, report = solver.solve_local(graph=graphs.build('absence'),
                                          scenario=capabilities.Scenario(),
                                          drifted_keys=('lighting',),
                                          current_members=('yolo11n-person',))
    assert report['escalated'] is True
    assert report['escalation_reason'] == '漂移覆盖全部需求'
    assert solution.chosen is not None


def test_without_an_index_hit_the_whole_graph_is_reconsidered():
    solution, report = solver.solve_local(graph=graphs.build('intrusion'),
                                          scenario=capabilities.Scenario(),
                                          drifted_keys=('unknown_attribute',),
                                          current_members=CURRENT)
    assert report['escalated'] is True
    assert report['affected'] == []


def test_missing_current_members_cannot_be_kept_so_the_engine_escalates():
    solution, report = solver.solve_local(graph=graphs.build('intrusion'),
                                          scenario=capabilities.Scenario(),
                                          drifted_keys=('lighting',),
                                          current_members=())
    assert report['escalated'] is True
    assert solution.chosen is not None
