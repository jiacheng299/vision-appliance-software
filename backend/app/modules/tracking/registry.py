"""策略注册表：只登记真实存在的策略，未安装的学习型策略如实标注。

多智能体强化学习关联策略在这里占一个位置，但 installed=False：仓库里没有
训练环境与权重，因此接口存在、能力不存在。任何试图创建未安装策略的调用都会
失败，而不是悄悄回退到启发式并假装成功。
"""
from dataclasses import dataclass
import importlib

from ...shared.errors import Error
from .heuristic import HeuristicIoUTracker
from .policy import TrackerPolicy


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


def _external(spec):
    """Load `module:attribute` as a third-party policy (e.g. a trained MARL policy).

    The spec is deliberately explicit: no directory scanning, no implicit import
    from user data. The imported object must satisfy the TrackerPolicy protocol,
    otherwise it is refused rather than failing later inside the rule loop.
    """
    module_name, _, attribute = spec.partition(':')
    if not module_name or not attribute:
        raise Error(422, 'tracker_policy_spec_invalid',
                    '外部追踪策略需写成 module:attribute 形式。')
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        raise Error(503, 'tracker_policy_unavailable',
                    f'追踪策略模块 {module_name} 无法导入，请确认已安装。') from None
    factory = getattr(module, attribute, None)
    if factory is None:
        raise Error(503, 'tracker_policy_unavailable',
                    f'模块 {module_name} 中没有 {attribute}。')
    try:
        policy = factory()
    except Exception as error:
        raise Error(503, 'tracker_policy_unavailable',
                    f'追踪策略初始化失败：{error}') from None
    if not isinstance(policy, TrackerPolicy):
        raise Error(503, 'tracker_policy_incompatible',
                    '外部追踪策略必须实现 name / reset / decide / describe。')
    return policy


def create(name='heuristic-iou', **kwargs):
    """Instantiate a policy by registry name or explicit `module:attribute` spec."""
    if name and name not in BUILTIN and name not in RESERVED and ':' in name:
        return _external(name)
    entry = info(name)
    if not entry.installed:
        raise Error(503, 'tracker_policy_not_installed',
                    f'追踪策略「{entry.label}」尚未安装，不能用于运行。')
    if name == 'heuristic-iou':
        return HeuristicIoUTracker()
    raise Error(503, 'tracker_policy_not_installed', '追踪策略实现缺失。')


_DESCRIBED = {}


def describe_active(spec):
    """What the configured policy actually resolves to, cached for the process.

    Used by the read-only status endpoint: it answers "what is running now"
    rather than "what does the catalogue contain". An external policy is
    instantiated once here (that is the only way to describe it), so a heavy
    policy costs one construction per process, not one per request.
    """
    if spec in _DESCRIBED:
        return _DESCRIBED[spec]
    entry = BUILTIN.get(spec) or RESERVED.get(spec)
    result = {'spec': spec, 'available': False, 'name': spec, 'kind': entry.kind if entry else 'external',
              'label': entry.label if entry else spec, 'external': bool(entry is None),
              'detail': None, 'reason': None}
    try:
        policy = create(spec)
    except Error as error:
        result['reason'] = error.message
        _DESCRIBED[spec] = result
        return result
    result['available'] = True
    result['name'] = getattr(policy, 'name', spec)
    try:
        result['detail'] = policy.describe()
    except Exception:  # 描述失败不影响"策略确实已装载"这一事实
        result['detail'] = None
    _DESCRIBED[spec] = result
    return result


def forget(spec=None):
    """Drop cached descriptions (tests and configuration reloads)."""
    if spec is None:
        _DESCRIBED.clear()
    else:
        _DESCRIBED.pop(spec, None)
