"""路由状态机：基线建立、漂移提议、无替代时的保守、候选影子验证与人工取消。"""
import time

import pytest
from dataclasses import replace

from app.modules.routing import state as routing_state
from app.modules.routing.capability import Capability
from app.modules.routing.models import RouteDecision, RouteState

ACTOR = 'workspace'


@pytest.fixture
def seeded(app):
    from app.shared.models import Source
    from app.modules.agents.models import Agent
    with app.state.sessions() as db:
        db.add(Source(id='cam', name='摄像头', kind='camera', status='online',
                      width=960, height=540, fps=15.0))
        db.add(Agent(id='agent', name='任务', description='', owner_id=ACTOR))
        db.commit()
    return app


def propose(app, **kwargs):
    with app.state.sessions() as db:
        view = routing_state.propose(db, 'agent', ACTOR, channel_id='ch', source_id='cam',
                                     rule='absence', **kwargs)
        db.commit()
        return view


def glare_attribute(app, label='strong_glare'):
    from app.modules.semantics import service as semantics
    from app.modules.semantics.schemas import AttributeInput
    with app.state.sessions() as db:
        semantics.upsert_attribute(db, 'cam', 'lighting',
                                   AttributeInput(value={'label': label}, source_kind='frame',
                                                  observed_at=time.time(),
                                                  confidence=0.85,
                                                  hard_expiry_at=time.time() + 3600))
        db.commit()


def set_active_since(app, seconds_ago):
    with app.state.sessions() as db:
        row = db.query(RouteState).first()
        row.active_since = time.time() - seconds_ago
        db.commit()


def advance(app, verdict='detected', **kwargs):
    kwargs.setdefault('eval_interval_seconds', 0.0)
    with app.state.sessions() as db:
        view = routing_state.advance_window(db, 'agent', ACTOR, channel_id='ch', source_id='cam',
                                            rule='absence', verdict=verdict, **kwargs)
        db.commit()
        return view


def test_first_proposal_establishes_a_baseline_route_version(seeded):
    view = propose(seeded)
    assert view.active_members == ['yolo11n-person']
    assert view.active_version == 'route-v1'
    assert view.mode == 'stable'
    assert view.delta_j == pytest.approx(0.0)
    with seeded.state.sessions() as db:
        kinds = [row.kind for row in db.query(RouteDecision).all()]
    assert kinds == ['baseline']


def test_repeated_proposal_without_drift_keeps_the_route(seeded):
    propose(seeded)
    second = propose(seeded)
    assert second.mode == 'stable'
    assert second.active_version == 'route-v1'
    assert second.drift == []


def test_a_hard_failure_without_an_alternative_stays_put_and_says_so(seeded):
    glare_attribute(seeded, 'daylight')
    propose(seeded)
    glare_attribute(seeded, 'strong_glare')
    view = propose(seeded)
    assert view.mode == 'stable'
    assert view.active_version == 'route-v1'
    assert view.active_members == ['yolo11n-person']
    assert view.candidate_members is None
    assert view.drift and view.drift[0].kind == 'confirmed'
    with seeded.state.sessions() as db:
        last = db.query(RouteDecision).order_by(RouteDecision.sequence.desc()).first()
    assert last.kind == 'blocked'
    assert '没有可行组合' in last.reason


def test_expiry_only_produces_a_notice_not_a_route_change(seeded):
    from app.modules.semantics import service as semantics
    from app.modules.semantics.schemas import AttributeInput
    glare_attribute(seeded, 'snow')
    propose(seeded)
    with seeded.state.sessions() as db:
        semantics.upsert_attribute(db, 'cam', 'lighting',
                                   AttributeInput(value={'label': 'snow'}, source_kind='frame',
                                                  observed_at=time.time() - 5000,
                                                  confidence=0.9, tau_seconds=10,
                                                  hard_expiry_at=time.time() - 4000))
        db.commit()
    view = propose(seeded)
    assert any('过期' in notice for notice in view.notices)
    assert view.mode == 'stable'


def strong_table():
    """A table where a second, better detector is actually installed."""
    from app.modules.routing import capability as capabilities
    stronger = replace(capabilities.get('yolo11s-person'), installed=True,
                       memory_mb=400.0, cpu_ms=60.0, label='YOLO11s 人员检测')
    return {**capabilities.table(), 'yolo11s-person': stronger}


def test_a_better_installed_candidate_enters_verification_after_the_dwell_time(seeded):
    propose(seeded)
    set_active_since(seeded, 1000.0)
    view = propose(seeded, table=strong_table())
    assert view.mode == 'candidate'
    assert view.candidate_members == ['yolo11s-person']
    assert view.delta_j > 0


def test_satisfied_shadow_validation_waits_for_takeover_capability(seeded):
    propose(seeded)
    set_active_since(seeded, 1000.0)
    table = strong_table()
    entered = propose(seeded, table=table)
    assert entered.mode == 'candidate'
    first = advance(seeded, verdict='detected', table=table)
    assert first.active_version == 'route-v1'
    second = advance(seeded, verdict='detected', table=table)
    assert second.active_version == 'route-v1'
    assert second.active_members == ['yolo11n-person']
    assert second.mode == 'candidate'
    assert second.candidate_members == ['yolo11s-person']
    with seeded.state.sessions() as db:
        decision = db.query(RouteDecision).order_by(RouteDecision.sequence.desc()).first()
    assert decision.action == 'hold'
    assert decision.reason == '影子验证已满足，等待接管能力'


def test_pending_candidate_version_binds_active_version_and_member_digest(seeded):
    propose(seeded)
    set_active_since(seeded, 1000.0)
    propose(seeded, table=strong_table())
    with seeded.state.sessions() as db:
        row = db.query(RouteState).first()
        candidate = routing_state.pending_candidate(row)
        assert candidate.members == ('yolo11s-person',)
        assert candidate.version.startswith('route-v1+candidate-')
        row.candidate_members = ['another-person']
        assert routing_state.pending_candidate(row).version != candidate.version
        row.candidate_members = None
        assert routing_state.pending_candidate(row) is None


def test_route_judgments_follow_the_eval_cadence(seeded):
    """窗口照常累计证据，但进入/取消/切换的判断按节奏执行。"""
    propose(seeded)
    set_active_since(seeded, 1000.0)
    table = strong_table()
    entered = propose(seeded, table=table)
    assert entered.mode == 'candidate'
    early = advance(seeded, verdict='detected', table=table, eval_interval_seconds=600.0)
    assert early.mode == 'candidate'
    assert early.valid_windows == 1
    with seeded.state.sessions() as db:
        decision = db.query(RouteDecision).order_by(RouteDecision.sequence.desc()).first()
        assert '仅累计证据' in decision.reason
        row = db.query(RouteState).first()
        row.last_eval_at = time.time() - 700
        db.commit()
    due = advance(seeded, verdict='detected', table=table, eval_interval_seconds=600.0)
    assert due.valid_windows == 2
    with seeded.state.sessions() as db:
        decision = db.query(RouteDecision).order_by(RouteDecision.sequence.desc()).first()
    assert decision.reason == '影子验证已满足，等待接管能力'


def test_an_insufficient_window_does_not_count_towards_the_switch(seeded):
    propose(seeded)
    set_active_since(seeded, 1000.0)
    table = strong_table()
    propose(seeded, table=table)
    view = advance(seeded, verdict='insufficient', table=table)
    assert view.valid_windows == 0
    assert view.active_version == 'route-v1'
    assert view.mode == 'candidate'


def test_auman_can_cancel_a_pending_candidate(seeded):
    propose(seeded)
    set_active_since(seeded, 1000.0)
    propose(seeded, table=strong_table())
    with seeded.state.sessions() as db:
        view = routing_state.cancel_candidate(db, 'agent', ACTOR, channel_id='ch', source_id='cam')
        db.commit()
    assert view.mode == 'stable'
    assert view.active_version == 'route-v1'
    with seeded.state.sessions() as db:
        assert db.query(RouteDecision).order_by(RouteDecision.sequence.desc()).first().action == 'cancel'


def test_cancelling_without_a_candidate_is_refused(seeded):
    from app.shared.errors import Error
    propose(seeded)
    with seeded.state.sessions() as db:
        with pytest.raises(Error) as error:
            routing_state.cancel_candidate(db, 'agent', ACTOR, channel_id='ch', source_id='cam')
    assert error.value.code == 'route_no_candidate'


def test_observation_windows_without_a_route_state_are_ignored(seeded):
    assert advance(seeded) is None


def test_scenario_ignores_metrics_from_an_insufficient_window(seeded):
    from app.modules.semantics.models import ObservationRecord
    with seeded.state.sessions() as db:
        db.add(ObservationRecord(id='observation-insufficient', agent_id='agent', actor_id=ACTOR,
                                 source_id='cam', task_key='person/absence', window_start=0.0,
                                 window_end=30.0, verdict='insufficient',
                                 metrics={'target_scale_px': 8.0, 'brightness': 0.01,
                                          'blur_score': 1.0}))
        db.commit()
    with seeded.state.sessions() as db:
        scenario, _profile = routing_state._scenario(db, 'cam', 'absence')
    assert scenario.target_px is None
    assert scenario.brightness is None
    assert scenario.blur is None


def test_latest_evidence_ignores_newer_candidate_observations(seeded):
    from app.modules.routing.service import _latest_evidence
    from app.modules.semantics.models import ObservationRecord
    with seeded.state.sessions() as db:
        db.add(ObservationRecord(id='active-evidence', agent_id='agent', actor_id=ACTOR,
                                 source_id='cam', task_key='person/absence', window_start=0.0,
                                 window_end=30.0, verdict='detected',
                                 metrics={'target_scale_px': 32.0}))
        db.add(ObservationRecord(id='candidate-evidence', agent_id='agent', actor_id=ACTOR,
                                 source_id='cam', task_key='person/absence', window_start=30.0,
                                 window_end=60.0, verdict='not_detected', route_role='candidate',
                                 metrics={'target_scale_px': 999.0, 'brightness': 0.01}))
        db.commit()
        active = db.query(ObservationRecord).filter_by(id='active-evidence').one()
        metrics, evidence, fell_back = _latest_evidence(db, 'cam', 'person/absence')
        assert active.route_role == 'active'
    assert evidence.id == 'active-evidence'
    assert metrics == {'target_scale_px': 32.0}
    assert fell_back is False


def test_active_route_falls_back_to_the_revision_version(seeded):
    with seeded.state.sessions() as db:
        version, members = routing_state.active_route(db, 'agent', ACTOR, 'ch', 'cam',
                                                      revision_no=3)
    assert version == 'local-r3'
    assert members is None

def test_a_plain_refresh_reports_no_escalation(seeded):
    propose(seeded)
    view = propose(seeded)
    assert view.escalated is True            # 单一需求图无法局部化
    assert view.notices == []                # 但没有漂移时不该给出升级提示
    with seeded.state.sessions() as db:
        assert db.query(RouteDecision).order_by(RouteDecision.sequence.desc()).first().kind == 'refresh'