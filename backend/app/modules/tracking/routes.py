"""Read the tracker policy registry, including honestly uninstalled slots."""
from fastapi import APIRouter
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


class PolicyPage(DTO):
    items: list[PolicyView]
    active: str
    notice: str


@router.get('/tracking/policies', response_model=PolicyPage)
def read_policies():
    return PolicyPage(items=[PolicyView(**item) for item in registry.describe()],
                      active='heuristic-iou',
                      notice='关联策略可替换；多智能体强化学习策略尚未安装，'
                             '本机仍使用固定机位 IoU/中心距关联。')
