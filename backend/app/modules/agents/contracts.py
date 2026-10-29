"""Public DTOs consumed by B. External providers own execution, events and exports."""
from typing import Literal
from pydantic import Field, StrictBool, model_validator
from ...schemas import DTO
from .schemas import RevisionConfig, CapabilityRef, Region

Origin = Literal['real', 'mock']
RunState = Literal['queued', 'starting', 'running', 'reconnecting', 'stopping', 'stopped', 'completed', 'failed', 'canceled']
ACTIVE_STATES = {'queued', 'starting', 'running', 'reconnecting', 'stopping'}


class CapabilityItem(DTO):
    name: str
    reference: CapabilityRef
    targets: list[str]
    rules: list[str]
    requires_region: list[str] = Field(default_factory=list)
    requires_duration: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    parameter_keys: list[str] = Field(default_factory=list)


class CapabilityCatalog(DTO):
    items: list[CapabilityItem]
    fingerprint: str
    data_origin: Origin = 'real'


class Assessment(DTO):
    verdict: Literal['executable', 'clarification_required', 'unsupported', 'insufficient_evidence']
    missing_conditions: list[str] = Field(default_factory=list)
    unsupported_conditions: list[str] = Field(default_factory=list)
    evidence_limitations: list[str] = Field(default_factory=list)
    capability_fingerprint: str
    chosen_capabilities: list[CapabilityRef] = Field(default_factory=list)
    data_origin: Origin = 'real'


class ValidationDTO(Assessment):
    id: str
    revision_id: str
    config_hash: str
    created_at: str
    expires_at: str


class VersionCommand(DTO):
    row_version: int = Field(ge=1, strict=True)


class ConfirmationInput(VersionCommand):
    validation_id: str = Field(min_length=1, max_length=80)
    config_hash: str = Field(min_length=64, max_length=64)
    limitations_acknowledged: StrictBool


class SourceSnapshot(DTO):
    id: str
    row_version: int
    kind: Literal['file', 'camera']
    sha256: str | None
    width: int | None
    height: int | None
    duration_ms: int | None


class RunDTO(DTO):
    id: str
    agent_id: str
    revision_id: str
    revision_no: int
    channel_id: str
    channel_name: str
    source_id: str
    state: RunState
    started_at: str | None = None
    created_at: str | None = None
    ended_at: str | None = None
    last_heartbeat_at: str | None = None
    processed_media_ms: int | None = None
    selected_duration_ms: int | None = None
    start_media_ms: int | None = None
    end_media_ms: int | None = None
    source_kind: Literal['file', 'camera']
    recording_available: bool = False
    config_snapshot: RevisionConfig
    source_snapshot: SourceSnapshot | None = None
    error_code: str | None = None
    message: str = ''
    baseline_run_id: str | None = None
    alert_state: Literal['normal', 'absence'] = 'normal'
    alert_started_at: str | None = None
    data_origin: Origin = 'real'


class RunPage(DTO):
    items: list[RunDTO]
    data_origin: Origin = 'real'


class ChannelOperation(DTO):
    channel_id: str
    source_id: str | None = None
    state: Literal['pending', 'stopping_old', 'starting_new', 'succeeded', 'failed', 'canceled']
    old_run_id: str | None = None
    new_run_id: str | None = None
    message: str = ''


class OperationDTO(DTO):
    id: str
    agent_id: str
    kind: Literal['start', 'stop', 'apply']
    state: Literal['pending', 'running', 'succeeded', 'partial_failed', 'failed', 'canceled']
    channels: list[ChannelOperation]
    message: str = ''
    data_origin: Origin = 'real'


class StartInput(DTO):
    revision_id: str = Field(min_length=1, max_length=80)
    channel_ids: list[str] = Field(min_length=1, max_length=16)
    expected_active_run_ids: list[str] = Field(default_factory=list, max_length=64)
    @model_validator(mode='after')
    def unique(self):
        if len(set(self.channel_ids)) != len(self.channel_ids) or len(set(self.expected_active_run_ids)) != len(self.expected_active_run_ids):
            raise ValueError('Duplicate scope ids')
        return self


class RetestInput(VersionCommand):
    baseline_run_id: str = Field(min_length=1, max_length=80)


class AgentEventDTO(DTO):
    id: str
    agent_id: str
    run_id: str
    revision_id: str
    source_id: str
    channel_id: str
    occurred_at: str
    updated_at: str
    row_version: int
    event_type: str
    severity: str
    reason: str
    evidence_status: Literal['pending', 'ready', 'partial', 'missing', 'failed', 'expired']
    review_status: Literal['unreviewed', 'correct', 'false_positive']
    feedback_reason: str = ''
    start_media_ms: int | None = None
    end_media_ms: int | None = None
    data_origin: Origin = 'real'


class EvidenceDTO(DTO):
    id: str
    kind: Literal['image', 'clip']
    state: Literal['pending', 'ready', 'missing', 'failed', 'expired']
    message: str = ''


class FeedbackDTO(DTO):
    id: str
    event_id: str
    label: Literal['correct', 'false_positive']
    reason: str
    created_at: str
    author_id: str


class EventDetail(AgentEventDTO):
    evidence: list[EvidenceDTO]
    feedback_history: list[FeedbackDTO]


class AgentEventPage(DTO):
    items: list[AgentEventDTO]
    next_cursor: str | None = None
    stream_cursor: str
    updated_at: str
    resync_required: bool = False
    data_origin: Origin = 'real'
    today_count: int | None = None
    pending_review_count: int | None = None


class FeedbackInput(DTO):
    label: Literal['correct', 'false_positive']
    reason: str = Field(default='', max_length=2000)
    row_version: int = Field(ge=1, strict=True)


class MissedInput(DTO):
    run_id: str = Field(min_length=1, max_length=80)
    event_type: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=4000)
    start_media_ms: int | None = Field(default=None, ge=0, strict=True)
    end_media_ms: int | None = Field(default=None, gt=0, strict=True)
    occurred_at: str | None = Field(default=None, max_length=80)


class MissedDTO(MissedInput):
    id: str
    agent_id: str
    revision_id: str
    source_id: str
    channel_id: str
    evidence_message: str
    created_at: str
    data_origin: Origin = 'real'


class MissedPage(DTO):
    items: list[MissedDTO]
    data_origin: Origin = 'real'


class TargetBox(DTO):
    id: str
    label: str
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(ge=0, le=1)
    height: float = Field(ge=0, le=1)


class PlaybackDTO(DTO):
    id: str
    agent_id: str
    run_id: str | None = None
    protocol: Literal['file', 'hls', 'webrtc', 'mock']
    playback_url: str | None = None
    expires_at: str
    message: str = ''
    regions: list[Region] = Field(default_factory=list)
    targets: list[TargetBox] = Field(default_factory=list)
    observed_at: str | None = None
    media_origin_ms: int = 0
    duration_ms: int | None = None
    data_origin: Origin = 'real'


class ComparisonDTO(DTO):
    baseline_run_id: str
    candidate_run_id: str
    comparable: bool
    limitation: str
    baseline: dict[str, int]
    candidate: dict[str, int]
    data_origin: Origin = 'real'


class ExportInput(DTO):
    run_ids: list[str] = Field(min_length=1, max_length=100)
    contents: list[Literal['report', 'images', 'clips']] = Field(min_length=1, max_length=3)
    destination: Literal['browser', 'host'] = 'browser'
    destination_alias: str | None = Field(default=None, min_length=1, max_length=128)
    @model_validator(mode='after')
    def destination_scope(self):
        if (self.destination == 'host') != (self.destination_alias is not None):
            raise ValueError('Host destination requires an approved alias; browser cannot accept a host alias')
        return self


class ExportDestination(DTO):
    kind: Literal['browser', 'host']
    alias: str | None = None
    label: str


class ExportDestinations(DTO):
    items: list[ExportDestination]
    data_origin: Origin = 'real'


class ExportDTO(DTO):
    id: str
    agent_id: str
    state: Literal['queued', 'collecting', 'rendering', 'packaging', 'succeeded', 'failed', 'canceled']
    message: str
    completed_items: int
    total_items: int | None = None
    download_url: str | None = None
    data_origin: Origin = 'real'


class WorkspaceDTO(DTO):
    agent_id: str
    runs: list[RunDTO]
    runtime_available: bool
    runtime_error: str = ''
    observed_at: str
    data_origin: Origin = 'real'


class RuntimeCommand(DTO):
    kind: Literal['start', 'stop', 'apply']
    agent_id: str
    revision_id: str | None = None
    revision_no: int | None = None
    config: RevisionConfig | None = None
    channel_ids: list[str] = Field(default_factory=list)
    expected_active_run_ids: list[str] = Field(default_factory=list)
    stop_run_id: str | None = None
    stop_channel_id: str | None = None
    validation_id: str | None = None
    confirmation_id: str | None = None
    capability_fingerprint: str | None = None
    baseline_run_id: str | None = None
    source_kinds: dict[str, Literal['file', 'camera']] = Field(default_factory=dict)
    source_snapshots: list[SourceSnapshot] = Field(default_factory=list)


class EmptyResult(DTO):
    ok: bool = True


class EnvironmentDTO(DTO):
    data_origin: Origin
    message: str


class AgentReference(DTO):
    reference_kind: Literal['agent','template'] = 'agent'
    agent_id: str
    agent_name: str
    revision_id: str
    revision_no: int
    revision_state: Literal['draft', 'published']
    channel_ids: list[str]
    archived: bool
    runtime_checked: bool
    active_run_ids: list[str] | None


class ReferencePage(DTO):
    items: list[AgentReference]
    next_cursor: str | None = None
    data_origin: Origin = 'real'


class DemoScenario(DTO):
    scenario: Literal['normal', 'model_unavailable', 'video_disconnected', 'events_disconnected', 'start_failed', 'resource_queued', 'stop_failed', 'duplicate_events', 'insufficient_evidence', 'run_failed', 'export_failed']
    run_id: str | None = None


class ExecutionSummary(DTO):
    """Workspace totals supplied by the owner of Run/Event data, never invented."""
    data_origin: Origin = 'real'
    active_runs: int | None = None
    running: int | None = None
    waiting: int | None = None
    completed: int | None = None
    failed: int | None = None
    today_events: int | None = None
    recent_events: list[AgentEventDTO] = Field(default_factory=list)
