from typing import Literal
from pydantic import Field, StrictBool, model_validator
from ...schemas import DTO
from ..agents.schemas import CapabilityRef, RevisionConfig, ChannelConfig
from ..agents.contracts import CapabilityItem

Usage = Literal['requirement_parse', 'multimodal_analysis']


class TemplateInput(DTO):
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9._-]+$')
    targets: list[str] = Field(min_length=1, max_length=100)
    rules: list[str] = Field(min_length=1, max_length=100)
    requires_region: list[str] = Field(default_factory=list, max_length=100)
    requires_duration: list[str] = Field(default_factory=list, max_length=100)
    defaults: dict[str, str | int | float | bool | None] = Field(default_factory=dict, max_length=50)
    limitations: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def coherent(self):
        for values in (self.targets, self.rules, self.requires_region, self.requires_duration, self.limitations):
            if len(values) != len(set(values)) or any(not v.strip() or len(v) > 2000 for v in values):
                raise ValueError('Empty, duplicate or excessively long template fields')
        if not set(self.requires_region + self.requires_duration) <= set(self.rules):
            raise ValueError('Required-condition rules must be declared supported rules')
        return self


class ModelInput(DTO):
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9._-]+$')
    runtime_type: str = Field(min_length=1, max_length=160)
    file_id: str = Field(min_length=1, max_length=80)
    template: TemplateInput


class ModelFileDTO(DTO):
    id: str
    filename: str
    size_bytes: int
    checksum: str
    created_at: str


class ModelDTO(ModelInput):
    id: str
    template_id: str
    checksum: str
    size_bytes: int
    validation: Literal['pending', 'passed', 'failed']
    validation_message: str
    status: Literal['available', 'archived']
    row_version: int
    data_origin: Literal['real', 'mock']
    created_at: str
    updated_at: str


class ModelPage(DTO):
    items: list[ModelDTO]
    next_cursor: str | None = None


class ModelVersionCommand(DTO):
    row_version: int = Field(ge=1, strict=True)


class ArchiveModel(ModelVersionCommand):
    acknowledge_history: StrictBool = False


class CapabilityPage(DTO):
    items: list[CapabilityItem]
    fingerprint: str
    next_cursor: str | None = None
    data_origin: Literal['real', 'mock']


class CapabilityCheck(DTO):
    capability_ref: CapabilityRef
    target: str = Field(max_length=160)
    rule: str = Field(max_length=160)


class CapabilityCheckResult(DTO):
    valid: bool
    unsupported_conditions: list[str]
    fingerprint: str
    data_origin: Literal['real', 'mock']


class Deployment(DTO):
    id: str
    name: str
    version: str
    usages: list[Usage]
    inputs: list[str]
    location: str
    health: Literal['healthy', 'unavailable', 'unknown']
    selected_usages: list[Usage] = Field(default_factory=list)


class Selection(DTO):
    usage: Usage
    deployment_id: str | None
    row_version: int


class DeploymentPage(DTO):
    items: list[Deployment]
    selections: list[Selection]
    data_origin: Literal['real', 'mock']


class SelectDeployment(DTO):
    deployment_id: str = Field(min_length=1, max_length=160)
    row_version: int = Field(ge=0, strict=True)


class ParseInput(DTO):
    requirement_text: str = Field(min_length=1, max_length=8000)


class ParseResult(DTO):
    target: str | None = None
    rule: str | None = None
    duration_seconds: int | None = Field(default=None, gt=0, le=86400)
    missing_conditions: list[str]
    limitations: list[str]
    deployment_id: str | None
    deployment_version: str | None
    data_origin: Literal['real', 'mock']


class EvaluateInput(DTO):
    config: RevisionConfig


class FixedTaskTemplate(DTO):
    id: str
    name: str
    target: str
    rule: str
    capability_ref: CapabilityRef
    requires_region: bool
    requires_duration: bool
    limitations: list[str]


class FixedTemplatePage(DTO):
    items: list[FixedTaskTemplate]
    fingerprint: str
    data_origin: Literal['real', 'mock']


class PlanInput(DTO):
    channel: ChannelConfig


class TemplateMatch(DTO):
    capability_ref: CapabilityRef
    target: str
    rule: str
    duration_seconds: int | None = Field(default=None, gt=0, le=86400)
    covers_all_requirements: StrictBool


class MultimodalAnalysis(DTO):
    target: str = Field(min_length=1, max_length=160)
    rule: str = Field(min_length=1, max_length=160)
    instruction: str = Field(min_length=1, max_length=8000)
    duration_seconds: int | None = Field(default=None, gt=0, le=86400)
    requires_region: StrictBool = False
    requires_duration: StrictBool = False
    verdict: Literal['executable', 'clarification_required', 'unsupported', 'insufficient_evidence']
    missing_conditions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class PlanResult(DTO):
    id: str
    strategy: Literal['template', 'multimodal']
    channel: ChannelConfig
    verdict: Literal['executable', 'clarification_required', 'unsupported', 'insufficient_evidence']
    missing_conditions: list[str]
    reason: str
    limitations: list[str]
    expires_at: str
    data_origin: Literal['real', 'mock']
