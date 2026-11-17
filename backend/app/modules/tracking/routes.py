"""Read the tracker policy catalogue and what is actually loaded right now."""
from typing import Any
from fastapi import APIRouter, Request
from pydantic import Field

from ...schemas import DTO
from . import registry

router = APIRouter(tags=['tracking'])


class PolicyView(DTO):
    name: str
    label: str
    kind: str
    installed: bool
    calibrated: bool
    requires: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ActivePolicyView(DTO):
    """配置里写的策略，与它实际装载出来的结果。"""
    spec: str
    available: bool
    name: str
    label: str
    kind: str
    external: bool
    detail: dict[str, Any] | None = None
    reason: str | None = None


class PolicyPage(DTO):
    items: list[PolicyView]
    active: str
    resolved: ActivePolicyView
    notice: str


@router.get('/tracking/policies', response_model=PolicyPage)
def read_policies(request: Request):
    spec = request.app.state.config.tracker_policy
    resolved = registry.describe_active(spec)
    if resolved['available'] and resolved['external']:
        notice = f'当前使用外部追踪策略 {resolved["name"]}（来自 {spec}）。'
    elif resolved['available']:
        notice = ('关联策略可替换；多智能体强化学习策略尚未安装，'
                  f'本机仍使用内置策略 {resolved["name"]}。')
    else:
        notice = f'配置的策略 {spec} 当前不可用：{resolved["reason"]}'
    return PolicyPage(items=[PolicyView(**item) for item in registry.describe()],
                      active=spec, resolved=ActivePolicyView(**resolved), notice=notice)
