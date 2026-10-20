from typing import Literal, Any
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import ipaddress

class DTO(BaseModel):
    model_config = ConfigDict(extra='forbid', from_attributes=True, str_strip_whitespace=True)

class ErrorDetail(DTO):
    code: str
    message: str
    details: Any = None
    retryable: bool
    request_id: str

class ErrorDTO(DTO):
    error: ErrorDetail

class SourceDTO(DTO):
    id: str
    name: str
    kind: Literal['file','camera']
    status: str
    created_at: str
    updated_at: str
    row_version: int
    observed_at: str | None = None
    address: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    duration_ms: int | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    preview_url: str | None = None
    thumbnail_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None

class CameraCreate(DTO):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    name: str = Field(min_length=1,max_length=160)
    kind: Literal['camera']
    address: str = Field(min_length=1,max_length=2048)
    username: str | None = Field(default=None,max_length=512)
    password: str | None = Field(default=None,max_length=512)

class SourcePatch(DTO):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    name: str | None = Field(default=None,min_length=1,max_length=160)
    address: str | None = Field(default=None,min_length=1,max_length=2048)
    username: str | None = Field(default=None,max_length=512)
    password: str | None = Field(default=None,max_length=512)
    row_version: int = Field(ge=1)

class UploadCreate(DTO):
    filename: str = Field(min_length=1,max_length=240)
    size_bytes: int = Field(gt=0,strict=True)
    @field_validator('filename')
    @classmethod
    def safe_name(cls, value):
        if any(c in value for c in ('/','\\',':','\x00')) or value in ('.','..') or any(ord(c)<32 for c in value):
            raise ValueError('Filename must be a basename')
        return value

class UploadComplete(DTO):
    name: str | None = Field(default=None,min_length=1,max_length=160)

class UploadDTO(DTO):
    id: str
    state: str
    received_bytes: int
    size_bytes: int
    source_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None

class SettingsPatch(DTO):
    values: dict[str,Any]
    row_version: int = Field(ge=1)

class SettingsDTO(DTO):
    section: str
    values: dict[str,Any]
    row_version: int

class General(DTO):
    system_name: str = Field(default='视觉一体机',min_length=1,max_length=100)
    timezone: str = 'Asia/Shanghai'
    auto_reconnect: StrictBool = True
    language: Literal['zh-CN'] = 'zh-CN'
    theme: Literal['light'] = 'light'
    @field_validator('timezone')
    @classmethod
    def timezone_known(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError,ValueError):
            raise ValueError('Unknown timezone')
        return value

class Storage(DTO):
    retention_days: int = Field(default=30,ge=1,le=3650,strict=True)
    max_upload_mb: int = Field(default=1024,ge=1,le=102400,strict=True)
    export_formats: list[Literal['json','csv','html']] = Field(default_factory=lambda:['json','csv','html'],min_length=1,max_length=3)

class Resources(DTO):
    max_concurrent_jobs: int = Field(default=1,ge=1,le=8,strict=True)
    connection_timeout_seconds: int = Field(default=10,ge=1,le=60,strict=True)
    reconnect_attempts: int = Field(default=3,ge=0,le=20,strict=True)

class Security(DTO):
    camera_allowed_networks: list[str] = Field(default_factory=lambda:['127.0.0.0/8','::1/128'],max_length=32)
    @field_validator('camera_allowed_networks')
    @classmethod
    def private_networks(cls, values):
        allowed = [ipaddress.ip_network(v) for v in ('127.0.0.0/8','10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','::1/128','fc00::/7')]
        result = []
        for value in values:
            network = ipaddress.ip_network(value,strict=True)
            if not any(network.version == base.version and network.subnet_of(base) for base in allowed):
                raise ValueError('Only explicit loopback or private camera CIDRs are permitted')
            result.append(str(network))
        return result

class SourcePage(DTO):
    items: list[SourceDTO]
    next_cursor: str | None = None

class SourceTestDTO(DTO):
    id: str
    state: str
    source_id: str
    error_code: str | None = None
    message: str | None = None

class PreviewDTO(DTO):
    session_id: str
    protocol: Literal['file','hls','webrtc']
    playback_url: str
    expires_at: str

class ServiceDTO(DTO):
    key: str
    name: str
    status: Literal['ready','unavailable','degraded']
    message: str
    observed_at: str

class RuntimeSample(DTO):
    observed_at: str
    cpu_percent: float
    memory_percent: float
    gpu_percent: float | None

class RuntimeDTO(RuntimeSample):
    disk: dict[str,int]
    sources: dict[str,int]
    runs: dict[str,int]
    services: list[ServiceDTO]
    models: list[dict] = []
    workers: list[dict] = []
    history: list[RuntimeSample] = []

class EventDTO(DTO):
    id: str
    event_type: str
    source_id: str | None
    source_name: str | None
    run_id: str | None
    revision_id: str | None
    occurred_at: str | None
    start_media_ms: int | None
    reason: str
    evidence_status: str
    review_status: str

class EventPage(DTO):
    items: list[EventDTO]
    next_cursor: str | None = None

class LogDTO(DTO):
    id: str
    occurred_at: str
    level: str
    module: str
    message: str

class LogPage(DTO):
    items: list[LogDTO]
    next_cursor: str | None = None

class DashboardDTO(DTO):
    counts: dict[str,int]
    sources: list[SourceDTO]
    recent_events: list[EventDTO]
    task_summary: dict[str,int]
