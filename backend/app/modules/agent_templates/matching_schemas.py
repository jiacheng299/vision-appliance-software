from typing import Annotated, Literal
from pydantic import Field
from ...schemas import DTO


class TemplateMatchRequest(DTO):
    requirement_text: str = Field(min_length=1, max_length=2000)


class TemplateMatcherStatus(DTO):
    configured: bool
    provider: Literal['deepseek'] = 'deepseek'
    model: str
    threshold: float


class TemplateMatchDecision(DTO):
    status: Literal['matched', 'no_match']
    template_id: str | None = Field(max_length=80)
    template_revision_id: str | None = Field(max_length=80)
    confidence: float = Field(ge=0, le=1, strict=True, allow_inf_nan=False)
    reason: str = Field(min_length=1, max_length=2000)
    uncovered_requirements: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(max_length=32)


class TemplateMatchResult(TemplateMatchDecision):
    provider: Literal['deepseek'] = 'deepseek'
    model: str
