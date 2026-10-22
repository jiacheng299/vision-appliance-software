from typing import Annotated, Literal
from pydantic import Field, model_validator
from ...schemas import DTO
from ...shared.models import uid


Coordinate = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class Region(DTO):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(default='', max_length=80)
    points: list[tuple[Coordinate, Coordinate]] = Field(min_length=3, max_length=64)

    @model_validator(mode='after')
    def simple_polygon(self):
        points = self.points
        if len(set(points)) != len(points):
            raise ValueError('Repeated polygon vertices')

        def cross(a, b, c):
            return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])

        def on_segment(a, b, p):
            return abs(cross(a, b, p)) < 1e-10 and min(a[0], b[0])-1e-10 <= p[0] <= max(a[0], b[0])+1e-10 and min(a[1], b[1])-1e-10 <= p[1] <= max(a[1], b[1])+1e-10

        def intersects(a, b, c, d):
            return (cross(a, b, c)*cross(a, b, d) < 0 and cross(c, d, a)*cross(c, d, b) < 0) or any((on_segment(a, b, c), on_segment(a, b, d), on_segment(c, d, a), on_segment(c, d, b)))

        n = len(points)
        for i in range(n):
            for j in range(i+1, n):
                if j == i+1 or (i == 0 and j == n-1):
                    continue
                if intersects(points[i], points[(i+1) % n], points[j], points[(j+1) % n]):
                    raise ValueError('Self intersecting polygon')
        area = sum(points[i][0]*points[(i+1) % n][1]-points[(i+1) % n][0]*points[i][1] for i in range(n))
        if abs(area) < 1e-10:
            raise ValueError('Polygon has zero area')
        # Adjacent edges may meet at a vertex but cannot double back over each other.
        for i in range(n):
            a, b, c = points[i-1], points[i], points[(i+1) % n]
            if abs(cross(a, b, c)) < 1e-10 and ((a[0]-b[0])*(c[0]-b[0])+(a[1]-b[1])*(c[1]-b[1])) > 0:
                raise ValueError('Overlapping polygon edges')
        return self


class CapabilityRef(DTO):
    model_id: str = Field(min_length=1, max_length=160)
    model_version: str = Field(min_length=1, max_length=80)
    template_id: str = Field(min_length=1, max_length=160)
    template_version: str = Field(min_length=1, max_length=80)


class ChannelConfig(DTO):
    channel_id: str = Field(default_factory=uid, min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    source_id: str | None = Field(default=None, min_length=1, max_length=80)
    requirement_text: str = Field(default='', max_length=8000)
    target: str = Field(default='', max_length=160)
    rule: str = Field(default='', max_length=160)
    duration_seconds: int | None = Field(default=None, gt=0, le=86400, strict=True)
    start_media_ms: int | None = Field(default=None, ge=0, strict=True)
    end_media_ms: int | None = Field(default=None, gt=0, strict=True)
    regions: list[Region] = Field(default_factory=list, max_length=32)
    capability_ref: CapabilityRef | None = None

    @model_validator(mode='after')
    def consistent(self):
        if (self.start_media_ms is None) != (self.end_media_ms is None):
            raise ValueError('Provide both media interval bounds')
        if self.start_media_ms is not None and self.end_media_ms <= self.start_media_ms:
            raise ValueError('Invalid media interval')
        if len({r.id for r in self.regions}) != len(self.regions):
            raise ValueError('Duplicate region ids')
        return self


class RevisionConfig(DTO):
    schema_version: Literal['1.0'] = '1.0'
    channels: list[ChannelConfig] = Field(default_factory=list, max_length=16)

    @model_validator(mode='after')
    def unique_channels(self):
        if len({c.channel_id for c in self.channels}) != len(self.channels):
            raise ValueError('Duplicate channel ids')
        return self


class AgentCreate(DTO):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default='', max_length=2000)
    config: RevisionConfig = Field(default_factory=RevisionConfig)


class AgentPatch(DTO):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(max_length=2000)
    row_version: int = Field(ge=1, strict=True)


class RevisionClone(DTO):
    base_revision_id: str = Field(min_length=1, max_length=80)
    row_version: int = Field(ge=1, strict=True)


class RevisionPatch(DTO):
    config: RevisionConfig
    row_version: int = Field(ge=1, strict=True)


class RevisionDTO(DTO):
    id: str
    agent_id: str
    revision_no: int
    base_revision_id: str | None
    state: Literal['draft', 'published']
    config: RevisionConfig
    row_version: int
    created_at: str
    updated_at: str
    latest_validation_id: str | None = None
    published_at: str | None = None
    baseline_run_id: str | None = None


class AgentDTO(DTO):
    id: str
    name: str
    description: str
    status: Literal['draft', 'ready', 'queued', 'running', 'stopping', 'stopped', 'failed', 'unknown', 'archived'] = 'draft'
    row_version: int
    created_at: str
    updated_at: str
    latest_revision: RevisionDTO
    archived_at: str | None = None
    desired_revision_id: str | None = None
    today_event_count: int | None = None
    latest_event_at: str | None = None
    data_origin: Literal['real', 'mock'] = 'real'
    active_run_count: int | None = None
    active_revision_nos: list[int] = Field(default_factory=list)
    failed_run_count: int | None = None
    pending_review_count: int | None = None


class AgentDetail(AgentDTO):
    revisions: list[RevisionDTO]
    execution_available: bool = False
    limitation: str = '模型能力评估和监测运行服务尚未接入。草稿可保存，暂不能启动监测。'


class AgentPage(DTO):
    items: list[AgentDTO]
    next_cursor: str | None = None
