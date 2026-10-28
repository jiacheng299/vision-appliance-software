from typing import Literal
from pydantic import Field
from ...schemas import DTO
from ...shared.monitoring_parameters import ParameterSetting
from ..agents.schemas import CapabilityRef, ChannelSource, AgentDetail, AgentDTO

class TemplateConfig(DTO):
    model_ref:CapabilityRef|None=None
    default_source:ChannelSource|None=Field(default=None,exclude_if=lambda v:v is None)
    parameters:list[ParameterSetting]=Field(default_factory=list,max_length=32)
    default_target:str=Field(default='',max_length=160)
    default_rule:str=Field(default='',max_length=160)
    title:str=Field(default='',max_length=160)
    summary:str=Field(default='',max_length=2000)

class TemplateCreate(DTO):
    name:str=Field(min_length=1,max_length=160)
    description:str=Field(default='',max_length=2000)
    config:TemplateConfig=Field(default_factory=TemplateConfig)

class TemplatePatch(TemplateCreate):
    row_version:int=Field(ge=1,strict=True)

class TemplateVersionCommand(DTO):
    row_version:int=Field(ge=1,strict=True)
    revision_id:str=Field(min_length=1,max_length=80)

class TemplateArchive(DTO):
    row_version:int=Field(ge=1,strict=True)
    archived:bool

class TemplateRevisionDTO(DTO):
    id:str
    template_id:str
    revision_no:int
    state:Literal['draft','published']
    config:TemplateConfig
    created_at:str
    published_at:str|None=None

class TemplateSource(DTO):
    id:str
    name:str
    kind:str
    status:str

class TemplateTaskDTO(DTO):
    agent:AgentDTO
    template_revision_id:str
    template_revision_no:int
    sources:list[TemplateSource]

class TemplateDTO(DTO):
    id:str
    name:str
    description:str
    row_version:int
    created_at:str
    updated_at:str
    archived_at:str|None=None
    imported_from_agent_id:str|None=None
    latest_revision:TemplateRevisionDTO
    published_revision:TemplateRevisionDTO|None=None
    task_count:int=0
    source_count:int=0

class TemplateDetail(TemplateDTO):
    revisions:list[TemplateRevisionDTO]

class TemplatePage(DTO):
    items:list[TemplateDTO]
    next_cursor:str|None=None

class TemplateTaskPage(DTO):
    items:list[TemplateTaskDTO]
    next_cursor:str|None=None

class TemplateSourcePage(DTO):
    items:list[TemplateSource]
    next_cursor:str|None=None

class TemplateTaskCreate(DTO):
    name:str=Field(min_length=1,max_length=160)
    description:str=Field(default='',max_length=2000)
    template_revision_id:str=Field(min_length=1,max_length=80)
    source:ChannelSource|None=None
    parameters:list[ParameterSetting]=Field(default_factory=list,max_length=32)
