"""任务需求图（M4）：需求节点、四类依赖边与属性反向索引。

需求图描述"要完成任务还缺什么"，而不是"现在有什么模型"。组合求解只允许
在满足依赖关系的成员集合上打分，因此缺一条串联边就得不到依赖满足量。
"""
from dataclasses import dataclass

SERIAL = 'serial'
JOINT = 'joint'
ALTERNATIVE = 'alternative'
TEMPORAL = 'temporal'
KINDS = (SERIAL, JOINT, ALTERNATIVE, TEMPORAL)
NODE_KINDS = ('detect', 'track', 'attribute', 'event', 'preprocess')


class GraphError(ValueError):
    """A requirement graph that cannot be executed as written."""


@dataclass(frozen=True)
class Requirement:
    key: str
    kind: str
    target: str
    weight: float = 1.0
    description: str = ''


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    kind: str
    seconds: float | None = None


class RequirementGraph:
    def __init__(self, requirements, edges=()):
        self.requirements = tuple(requirements)
        self.edges = tuple(edges)
        self._by_key = {item.key: item for item in self.requirements}
        self.validate()

    def validate(self):
        if not self.requirements:
            raise GraphError('需求图至少要有一个节点。')
        if len(self._by_key) != len(self.requirements):
            raise GraphError('需求节点重复。')
        for item in self.requirements:
            if item.kind not in NODE_KINDS:
                raise GraphError(f'未知需求类型：{item.kind}')
            if item.weight <= 0:
                raise GraphError('需求权重必须为正数。')
        seen = set()
        for edge in self.edges:
            if edge.kind not in KINDS:
                raise GraphError(f'未知依赖边类型：{edge.kind}')
            if edge.source not in self._by_key or edge.target not in self._by_key:
                raise GraphError('依赖边引用了不存在的节点。')
            if edge.source == edge.target:
                raise GraphError('依赖边不能指向自身。')
            if edge.kind == TEMPORAL and (edge.seconds is None or edge.seconds <= 0):
                raise GraphError('时序依赖必须给出正数持续时间。')
            if (edge.source, edge.target, edge.kind) in seen:
                raise GraphError('重复的依赖边。')
            seen.add((edge.source, edge.target, edge.kind))
        self.order()

    def order(self):
        """Topological order over ordering edges; a cycle is not executable."""
        outgoing = {}
        for edge in self.edges:
            if edge.kind in (SERIAL, TEMPORAL):
                outgoing.setdefault(edge.source, []).append(edge.target)
        order, visiting, done = [], set(), set()

        def visit(key):
            if key in done:
                return
            if key in visiting:
                raise GraphError('串联或时序依赖存在环，无法排序。')
            visiting.add(key)
            for following in outgoing.get(key, ()):
                visit(following)
            visiting.discard(key)
            done.add(key)
            order.append(key)

        for item in self.requirements:
            visit(item.key)
        # Post-order visits descendants first; reversing yields sources first.
        return order[::-1]

    @property
    def keys(self):
        return tuple(item.key for item in self.requirements)

    def weights(self):
        return {item.key: item.weight for item in self.requirements}

    def requirement(self, key):
        return self._by_key[key]

    def kind_of(self, key):
        return self._by_key[key].kind

    def dependencies(self):
        return self.edges

    def edges_into(self, key):
        return tuple(edge for edge in self.edges if edge.target == key)

    def required_keys(self):
        """Every declared requirement is required: alternatives live in edges, not nodes."""
        return self.keys


def build(rule, target='person', *, duration_seconds=None):
    """The requirement graph the current business rules actually need."""
    if rule == 'absence':
        return RequirementGraph([Requirement('person_detect', 'detect', target, 1.0,
                                             '监测区域内人员数量')])
    if rule == 'intrusion':
        return RequirementGraph(
            [Requirement('person_detect', 'detect', target, 0.5, '检测人员'),
             Requirement('person_track', 'track', target, 0.3, '跨帧关联同一目标'),
             Requirement('zone_intersect', 'event', target, 0.2, '轨迹与监测区域相交确认')],
            [Edge('person_detect', 'person_track', SERIAL),
             Edge('person_track', 'zone_intersect', TEMPORAL,
                  seconds=float(duration_seconds or 8.0))])
    raise GraphError(f'未知任务规则：{rule}')


# 属性 → 需求的反向索引（M4）；漂移判定沿此方向定位受影响子图。
ATTRIBUTE_REQUIREMENTS = {
    'lighting': ('person_detect',),
    'weather': ('person_detect',),
    'season_appearance': ('person_detect',),
    'occlusion': ('person_detect', 'person_track'),
    'camera_pose': ('person_detect', 'person_track'),
    'background_texture': ('person_detect',),
}


def affected_requirements(attribute_keys):
    """Attribute key → the requirement nodes whose evidence it supports."""
    affected = {}
    for key in attribute_keys:
        for requirement in ATTRIBUTE_REQUIREMENTS.get(key, ()):
            affected.setdefault(requirement, []).append(key)
    return affected
