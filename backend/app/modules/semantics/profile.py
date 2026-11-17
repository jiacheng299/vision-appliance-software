"""Time-decayed semantic attributes (式(1)) and their state semantics.

The single rule that matters: expired or unconfirmed evidence becomes unknown,
never the opposite fact. A strength of zero says "we no longer know", not "the
opposite is true".
"""
from dataclasses import dataclass
import math

STATE_VALID = 'valid'
STATE_EXPIRED = 'expired'
STATE_UNKNOWN = 'unknown'
STATE_CONFLICT = 'conflict'

# Attributes whose strength falls below this are still valid but carry little
# routing weight; they remain usable so a caller can decide its own floor.
WEAK_STRENGTH = 0.05


@dataclass(frozen=True)
class AttributeStrength:
    state: str
    strength: float
    usable: bool
    reason: str | None = None


def attribute_strength(*, observed_at: float, at: float, confidence: float,
                       tau_seconds: float | None = None,
                       hard_expiry_at: float | None = None,
                       conflict: bool = False) -> AttributeStrength:
    """式(1): q_a * exp(-(t - t_a) / tau_a) * I(t_a <= t < T_a).

    A record whose observation time is in the future is refused outright rather
    than clamped: a wrong clock must not silently become fresh evidence.
    """
    if not all(math.isfinite(value) for value in (observed_at, at, confidence)):
        return AttributeStrength(STATE_UNKNOWN, 0.0, False, 'non_finite_time')
    if confidence <= 0:
        return AttributeStrength(STATE_UNKNOWN, 0.0, False, 'no_confidence')
    if at < observed_at:
        return AttributeStrength(STATE_UNKNOWN, 0.0, False, 'timestamp_before_observation')
    if hard_expiry_at is not None and math.isfinite(hard_expiry_at) and at >= hard_expiry_at:
        return AttributeStrength(STATE_EXPIRED, 0.0, False, 'hard_expiry_reached')
    if tau_seconds is None or tau_seconds <= 0:
        strength = confidence
    else:
        if not math.isfinite(tau_seconds):
            return AttributeStrength(STATE_UNKNOWN, 0.0, False, 'non_finite_decay')
        strength = confidence * math.exp(-(at - observed_at) / tau_seconds)
    strength = min(1.0, max(0.0, strength))
    if conflict:
        return AttributeStrength(STATE_CONFLICT, strength, False, 'conflicting_sources')
    if strength <= 0:
        return AttributeStrength(STATE_EXPIRED, 0.0, False, 'decayed_to_zero')
    return AttributeStrength(STATE_VALID, strength, True, None)


def routing_attributes(views, at: float, minimum: float = 0.0) -> dict:
    """Only usable attributes above `minimum` may steer a route."""
    return {view.key: view for view in views
            if view.usable and view.strength >= minimum and view.state == STATE_VALID}


def attribute_changed(previous: float | None, current: float | None,
                      epsilon: float) -> bool:
    """A shift of at least `epsilon` counts as evidence the scene moved."""
    if previous is None or current is None:
        return False
    return abs(current - previous) >= epsilon
