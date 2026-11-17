"""追踪策略接口（为多智能体强化学习预留）。

本模块只定义契约，**不包含任何学习型策略**：仓库里没有 MARL 的训练环境，
也没有可用的策略权重。目的是把"换一个追踪器"变成配置问题而不是改代码问题，
并让观测/动作的形状先固定下来，方便在外部工程里训练再回来接。

观测（Observation）：一帧的检测结果（归一化坐标）+ 监测区域 + 可选画面指标。
动作（Decision）：轨迹与检测的关联、新目标入场、轨迹丢失。
状态（Track）：由框架持有，策略不直接改写，避免策略把状态改坏。
"""
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Detection:
    label: str
    x: float
    y: float
    width: float
    height: float
    confidence: float = 0.0

    def as_box(self):
        return {'label': self.label, 'x': self.x, 'y': self.y, 'width': self.width,
                'height': self.height, 'confidence': self.confidence}


@dataclass(frozen=True)
class Track:
    """只读视图：策略可以据此决策，但不能直接修改。"""
    id: str
    box: dict
    last_seen: float
    hits: int = 1
    missing_since: float | None = None


@dataclass(frozen=True)
class Observation:
    timestamp: float
    detections: tuple[Detection, ...] = ()
    roi: tuple = ()
    frame: dict = field(default_factory=dict)

    def box_of(self, index):
        return self.detections[index].as_box()


@dataclass(frozen=True)
class Decision:
    """策略输出：关联、入场与丢失。索引指向本次观测的检测列表。"""
    associations: tuple = ()      # ((track_id, detection_index), ...)
    new_detections: tuple = ()    # (detection_index, ...)
    lost: tuple = ()              # (track_id, ...)
    note: str = ''


@runtime_checkable
class TrackerPolicy(Protocol):
    """策略只需要实现 decide；轨迹状态由框架统一维护。"""
    name: str

    def reset(self) -> None: ...

    def decide(self, observation: Observation, tracks: tuple) -> Decision: ...

    def describe(self) -> dict: ...


def detection_from_box(box) -> Detection:
    return Detection(label=str(box.get('label', 'person')), x=float(box['x']), y=float(box['y']),
                     width=float(box['width']), height=float(box['height']),
                     confidence=float(box.get('confidence', 0.0) or 0.0))


def valid_person(box) -> bool:
    import math
    if not isinstance(box, dict) or box.get('label') != 'person':
        return False
    values = [box.get(key) for key in ('x', 'y', 'width', 'height')]
    return (all(type(value) in (int, float) and math.isfinite(value) for value in values)
            and values[2] > 0 and values[3] > 0)
