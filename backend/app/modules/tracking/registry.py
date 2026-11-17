"""策略注册表：只登记真实存在的策略，未安装的学习型策略如实标注。

多智能体强化学习关联策略在这里占一个位置，但 installed=False：仓库里没有
训练环境与权重，因此接口存在、能力不存在。任何试图创建未安装策略的调用都会
失败，而不是悄悄回退到启发式并假装成功。
"""
from dataclasses import dataclass

from ...shared.errors import Error
from .heuristic import HeuristicIoUTracker


@dataclass(frozen=True)
class PolicyInfo:
    name: str
    label: str
    kind: str
    installed: bool
    calibrated: bool
    requires: tuple = ()
    limitations: tuple = ()

    def as_dict(self):
        return {'name': self.name, 'label': self.label, 'kind': self.kind,
                'installed': self.installed, 'calibrated': self.calibrated,
                'requires': list(self.requires), 'limitations': list(self.limitations)}


BUILTIN = {
    'heuristic-iou': PolicyInfo(
        name='heuristic-iou', label='固定机位 IoU/中心距关联', kind='heuristic',
        installed=True, calibrated=True,
        limitations=('不做身份识别', '依赖固定机位', '快速交叉时可能交换轨迹')),
}

# 预留位：训练与权重都在外部工程，本仓库不包含。
RESERVED = {
    'marl-association': PolicyInfo(
        name='marl-association', label='多智能体强化学习关联策略（预留）', kind='learned',
        installed=False, calibrated=False,
        requires=('观测：归一化检测框与置信度', '动作：关联矩阵/入场/离场',
                  '训练环境与策略权重（不在本仓库）'),
        limitations=('本仓库没有训练循环与策略权重', '未接入前不得计入任何能力声明')),
}


def describe():
    return [BUILTIN['heuristic-iou'].as_dict(),
            RESERVED['marl-association'].as_dict()]


def info(name):
    entry = BUILTIN.get(name) or RESERVED.get(name)
    if entry is None:
        raise Error(404, 'tracker_policy_unknown', '未知的追踪策略。')
    return entry


def create(name='heuristic-iou', **kwargs):
    """Instantiate an installed policy; uninstalled ones fail loudly."""
    entry = info(name)
    if not entry.installed:
        raise Error(503, 'tracker_policy_not_installed',
                    f'追踪策略「{entry.label}」尚未安装，不能用于运行。')
    if name == 'heuristic-iou':
        return HeuristicIoUTracker()
    raise Error(503, 'tracker_policy_not_installed', '追踪策略实现缺失。')
