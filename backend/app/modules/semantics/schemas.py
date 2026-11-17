"""Contracts for the semantic profile and the valid-observation records."""
from typing import Any, Literal
from pydantic import Field, model_validator
from ...schemas import DTO

AttributeSource = Literal['device', 'frame', 'language', 'probe']
Verdict = Literal['detected', 'not_detected', 'insufficient']
GateStatus = Literal['pass', 'fail', 'unverified', 'not_applicable']

INTRINSIC_KEYS = frozenset({'resolution', 'lens', 'mount_position', 'field_of_view',
                            'stream', 'device_id'})


def _check_roi(points, field='roi'):
    for point in points:
        if len(point) != 2:
            raise ValueError(f'{field} points must be [x, y] pairs')
        if any(value < 0 or value > 1 for value in point):
            raise ValueError(f'{field} points must stay inside the normalised frame')
    return points


class IntrinsicInput(DTO):
    """固有层：由设备信息给出，不随时间衰减。"""
    values: dict[str, Any] = Field(default_factory=dict)
    view_version: str | None = Field(default=None, min_length=1, max_length=32)

    @model_validator(mode='after')
    def known_keys(self):
        unknown = set(self.values) - INTRINSIC_KEYS
        if unknown:
            raise ValueError('unsupported intrinsic keys: ' + ', '.join(sorted(unknown)))
        return self


class AttributeInput(DTO):
    """动态层：每一项都必须带来源、观测时刻与有效期。"""
    value: dict[str, Any]
    source_kind: AttributeSource
    observed_at: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    source_frame_ts: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    roi: list[list[float]] = Field(default_factory=list, max_length=64)
    confidence: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    tau_seconds: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    hard_expiry_at: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    conflict: bool = False

    @model_validator(mode='after')
    def coherent(self):
        _check_roi(self.roi)
        if self.hard_expiry_at is not None and self.observed_at is not None \
                and self.hard_expiry_at <= self.observed_at:
            raise ValueError('hard_expiry_at must be later than observed_at')
        return self


class AttributeView(DTO):
    key: str
    value: dict[str, Any]
    source_kind: str
    source_frame_ts: float | None = None
    roi: list[list[float]] = Field(default_factory=list)
    observed_at: float
    confidence: float
    tau_seconds: float | None = None
    hard_expiry_at: float | None = None
    stored_state: str
    state: str
    strength: float
    usable: bool
    reason: str | None = None
    version: int


class ProfileView(DTO):
    source_id: str
    view_version: str
    version: int
    intrinsic: dict[str, Any]
    runtime: dict[str, Any]
    attributes: list[AttributeView]
    evaluated_at: float
    updated_at: str


class ObservationMetrics(DTO):
    frame_count: int | None = Field(default=None, ge=0, strict=True)
    time_continuous: bool | None = None
    duration_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    actual_fps: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    max_gap_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    brightness: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    roi_visible_ratio: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    overexposure_ratio: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    blur_score: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    occlusion_ratio: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    target_scale_px: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class ObservationThresholds(DTO):
    min_fps: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    max_gap_seconds: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    min_window_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    min_roi_visible_ratio: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    max_overexposure_ratio: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    min_blur_score: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    max_occlusion_ratio: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    min_target_scale_px: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class Versions(DTO):
    route_version: str | None = Field(default=None, max_length=80)
    profile_version: int | None = Field(default=None, ge=0, strict=True)
    model_version: str | None = Field(default=None, max_length=80)


class ObservationInput(DTO):
    source_id: str = Field(min_length=1, max_length=80)
    run_id: str | None = Field(default=None, max_length=80)
    path_id: str | None = Field(default=None, max_length=80)
    task_key: str = Field(min_length=1, max_length=160)
    roi: list[list[float]] = Field(default_factory=list, max_length=64)
    window_start: float = Field(ge=0, allow_inf_nan=False)
    window_end: float = Field(ge=0, allow_inf_nan=False)
    detection_count: int = Field(default=0, ge=0, strict=True)
    path_complete: bool = True
    nodes_completed: list[str] = Field(default_factory=list, max_length=64)
    metrics: ObservationMetrics = Field(default_factory=ObservationMetrics)
    thresholds: ObservationThresholds = Field(default_factory=ObservationThresholds)
    versions: Versions = Field(default_factory=Versions)
    expected_versions: Versions | None = None

    @model_validator(mode='after')
    def coherent(self):
        _check_roi(self.roi)
        if self.window_end < self.window_start:
            raise ValueError('window_end must not precede window_start')
        return self


class GateView(DTO):
    name: str
    status: str
    value: float | int | None = None
    threshold: float | int | None = None
    reason: str | None = None


class ObservationView(DTO):
    id: str
    agent_id: str
    run_id: str | None = None
    source_id: str
    task_key: str
    roi: list[list[float]] = Field(default_factory=list)
    window_start: float
    window_end: float
    route_version: str | None = None
    profile_version: int | None = None
    model_version: str | None = None
    path_id: str | None = None
    verdict: Verdict
    detection_count: int
    metrics: ObservationMetrics
    thresholds: ObservationThresholds
    gates: list[GateView]
    reasons: list[str]
    created_at: str


class ObservationPage(DTO):
    items: list[ObservationView]
    next_cursor: str | None = None
    summary: dict[str, int]
