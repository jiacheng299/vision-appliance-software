"""式(1) 时效衰减与"过期转未知、不转相反事实"的状态语义。"""
import math
from types import SimpleNamespace

import pytest

from app.modules.semantics.profile import (STATE_CONFLICT, STATE_EXPIRED, STATE_UNKNOWN,
                                           STATE_VALID, attribute_changed, attribute_strength,
                                           routing_attributes)


def test_strength_follows_the_documented_decay_formula():
    result = attribute_strength(observed_at=100.0, at=160.0, confidence=0.9, tau_seconds=60.0)
    assert result.state == STATE_VALID
    assert result.strength == pytest.approx(0.9 * math.exp(-1.0), rel=1e-9)
    assert result.usable is True
    assert result.reason is None


def test_attribute_without_decay_holds_confidence_until_hard_expiry():
    fresh = attribute_strength(observed_at=100.0, at=159.0, confidence=0.8)
    assert fresh.state == STATE_VALID and fresh.strength == pytest.approx(0.8)
    expired = attribute_strength(observed_at=100.0, at=160.0, confidence=0.8,
                                 hard_expiry_at=160.0)
    assert expired.state == STATE_EXPIRED
    assert expired.strength == 0.0
    assert expired.usable is False


def test_expiry_yields_unknown_never_the_opposite_fact():
    result = attribute_strength(observed_at=1_000.0, at=2_000.0, confidence=0.95,
                                tau_seconds=60.0, hard_expiry_at=1_500.0)
    assert result.state == STATE_EXPIRED
    assert result.strength == 0.0
    assert result.reason == 'hard_expiry_reached'
    # Zero strength is "we no longer know", not "the opposite holds".
    assert result.usable is False


def test_future_observation_is_refused_instead_of_clamped():
    result = attribute_strength(observed_at=500.0, at=100.0, confidence=0.9, tau_seconds=60.0)
    assert result.state == STATE_UNKNOWN
    assert result.strength == 0.0
    assert result.reason == 'timestamp_before_observation'


def test_non_finite_times_and_zero_confidence_are_never_usable():
    cases = [dict(observed_at=float('nan'), at=1.0, confidence=0.5),
             dict(observed_at=1.0, at=float('inf'), confidence=0.5),
             dict(observed_at=1.0, at=2.0, confidence=0.0)]
    for case in cases:
        result = attribute_strength(**case)
        assert result.usable is False and result.strength == 0.0


def test_conflicting_sources_keep_the_state_and_lose_usability():
    result = attribute_strength(observed_at=10.0, at=20.0, confidence=0.9, tau_seconds=600.0,
                                conflict=True)
    assert result.state == STATE_CONFLICT
    assert result.usable is False
    assert result.strength > 0
    assert result.reason == 'conflicting_sources'


def view(key, strength, usable, state=STATE_VALID):
    return SimpleNamespace(key=key, strength=strength, usable=usable, state=state)


def test_only_usable_attributes_above_the_floor_steer_a_route():
    views = [view('lighting', 0.7, True),
             view('weather', 0.02, True),
             view('occlusion', 0.0, False, STATE_EXPIRED),
             view('season', 0.5, False, STATE_CONFLICT)]
    selected = routing_attributes(views, at=0.0, minimum=0.05)
    assert set(selected) == {'lighting'}


def test_change_detection_requires_known_values_and_an_epsilon_shift():
    assert attribute_changed(0.6, 0.9, 0.2) is True
    assert attribute_changed(0.6, 0.7, 0.2) is False
    assert attribute_changed(None, 0.9, 0.2) is False
    assert attribute_changed(0.9, None, 0.2) is False
