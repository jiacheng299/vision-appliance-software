"""组合路由的请求与响应契约。"""
from typing import Any
from pydantic import Field

from ...schemas import DTO


class RequirementView(DTO):
    key: str
    kind: str
    target: str
    weight: float
    description: str = ''


class EdgeView(DTO):
    source: str
    target: str
    kind: str
    seconds: float | None = None


class CapabilityView(DTO):
    id: str
    label: str
    kind: str
    target: str
    installed: bool
    calibrated: bool
    provides: list[str]
    quality: dict[str, float]
    bucket_quality: dict[str, dict[str, float]]
    cpu_ms: float
    memory_mb: float
    limitations: list[str]


class EvaluationView(DTO):
    combination_id: str
    label: str
    members: list[str]
    score: float | None = None
    coverage: float
    dependency: float
    conflict: float
    cost: float
    switch: float
    feasible: bool
    reasons: list[str]
    bucket: str


class ScenarioView(DTO):
    bucket: str
    saturated_ratio: float | None = None
    target_px: float | None = None
    brightness: float | None = None
    blur: float | None = None
    reasons: list[str] = Field(default_factory=list)


class RouteView(DTO):
    source_id: str
    rule: str
    profile_version: int
    scenario: ScenarioView
    graph: dict[str, Any]
    capabilities: list[CapabilityView]
    chosen: EvaluationView | None = None
    ranked: list[EvaluationView]
    blocked: list[EvaluationView]
    weights: dict[str, float]
    budgets: dict[str, float]
    min_quality: float
    notices: list[str]


class DriftView(DTO):
    attribute: str
    kind: str
    previous: str | None = None
    current: str | None = None
    reason: str


class RouteStateView(DTO):
    agent_id: str
    channel_id: str
    source_id: str
    rule: str
    active_members: list[str]
    active_version: str
    active_since: float | None = None
    mode: str
    candidate_members: list[str] | None = None
    candidate_score: float | None = None
    valid_windows: int
    hard_failure: bool
    delta_j: float | None = None
    drift: list[DriftView] = Field(default_factory=list)
    affected: list[str] = Field(default_factory=list)
    fixed: list[str] = Field(default_factory=list)
    escalated: bool = False
    escalation_reason: str | None = None
    chosen: EvaluationView | None = None
    notices: list[str] = Field(default_factory=list)
    updated_at: str


class RouteDecisionView(DTO):
    id: str
    kind: str
    action: str
    reason: str
    delta_j: float | None = None
    route_version: str | None = None
    source_id: str
    channel_id: str
    created_at: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ProposeInput(DTO):
    channel_id: str = Field(min_length=1, max_length=80)
    source_id: str = Field(min_length=1, max_length=80)
    rule: str = Field(default='absence', pattern='^(absence|intrusion)$')
    duration_seconds: float | None = Field(default=None, gt=0, le=86400, allow_inf_nan=False)


class PreheatView(DTO):
    """影子运行要付出的资源：两个会话并存的实测代价。"""
    available: bool
    reason: str | None = None
    model_path: str | None = None
    frames: int
    load_ms: float | None = None
    baseline_ms: float | None = None
    shadow_ms: float | None = None
    latency_delta_ms: float | None = None
    rss_before_mb: float | None = None
    rss_first_mb: float | None = None
    rss_after_mb: float | None = None
    rss_delta_mb: float | None = None
    rss_total_mb: float | None = None
    notes: list[str] = Field(default_factory=list)
    budget: dict[str, Any] = Field(default_factory=dict)
    budgets: dict[str, float] = Field(default_factory=dict)


class CancelInput(DTO):
    channel_id: str = Field(min_length=1, max_length=80)
    source_id: str = Field(min_length=1, max_length=80)
