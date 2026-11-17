"""需求图（M4）：四类依赖边、可执行性校验与属性反向索引。"""
import pytest

from app.modules.routing import graph as graphs
from app.modules.routing.graph import (ALTERNATIVE, Edge, GraphError, JOINT, Requirement,
                                       RequirementGraph, SERIAL, TEMPORAL)


def test_absence_needs_only_a_detector_and_intrusion_needs_a_full_chain():
    absence = graphs.build('absence')
    assert absence.keys == ('person_detect',)
    assert absence.dependencies() == ()

    intrusion = graphs.build('intrusion', duration_seconds=8.0)
    assert set(intrusion.keys) == {'person_detect', 'person_track', 'zone_intersect'}
    kinds = {(edge.source, edge.target): edge.kind for edge in intrusion.dependencies()}
    assert kinds[('person_detect', 'person_track')] == SERIAL
    assert kinds[('person_track', 'zone_intersect')] == TEMPORAL
    temporal, = [edge for edge in intrusion.dependencies() if edge.kind == TEMPORAL]
    assert temporal.seconds == 8.0
    assert intrusion.order().index('person_detect') < intrusion.order().index('zone_intersect')


def test_requirement_weights_default_to_one_and_drive_coverage():
    built = graphs.build('intrusion')
    weights = built.weights()
    assert pytest.approx(sum(weights.values())) == 1.0
    assert built.requirement('person_detect').kind == 'detect'
    assert built.requirement('zone_intersect').kind == 'event'


def test_unknown_rule_is_refused_instead_of_invented():
    with pytest.raises(GraphError):
        graphs.build('crowd_density')


def test_invalid_graphs_are_rejected_before_they_reach_the_solver():
    node = Requirement('a', 'detect', 'person')
    other = Requirement('b', 'event', 'person')
    with pytest.raises(GraphError, match='至少'):
        RequirementGraph([])
    with pytest.raises(GraphError, match='重复'):
        RequirementGraph([node, node])
    with pytest.raises(GraphError, match='不存在'):
        RequirementGraph([node], [Edge('a', 'missing', SERIAL)])
    with pytest.raises(GraphError, match='自身'):
        RequirementGraph([node], [Edge('a', 'a', SERIAL)])
    with pytest.raises(GraphError, match='未知需求类型'):
        RequirementGraph([Requirement('a', 'magic', 'person')])
    with pytest.raises(GraphError, match='正数'):
        RequirementGraph([node, other], [Edge('a', 'b', TEMPORAL, seconds=0)])
    with pytest.raises(GraphError, match='环'):
        RequirementGraph([node, other], [Edge('a', 'b', SERIAL), Edge('b', 'a', SERIAL)])
    with pytest.raises(GraphError, match='重复的依赖边'):
        RequirementGraph([node, other], [Edge('a', 'b', SERIAL), Edge('a', 'b', SERIAL)])


def test_joint_and_alternative_edges_are_expressible():
    people = Requirement('people', 'detect', 'person', .5)
    helmet = Requirement('helmet', 'attribute', 'person', .5)
    direct = Requirement('direct_event', 'event', 'person', 1.0)
    joint = RequirementGraph([people, helmet], [Edge('people', 'helmet', JOINT)])
    assert joint.dependencies()[0].kind == JOINT
    alternative = RequirementGraph([people, direct],
                                   [Edge('people', 'direct_event', ALTERNATIVE)])
    assert alternative.dependencies()[0].kind == ALTERNATIVE
    # Joining two objects requires both sides; a joint edge cannot name one node twice.
    with pytest.raises(GraphError):
        RequirementGraph([people, direct], [Edge('people', 'direct_event', JOINT),
                                           Edge('people', 'direct_event', JOINT)])


def test_attribute_reverse_index_points_from_profile_to_requirements():
    affected = graphs.affected_requirements(['lighting', 'occlusion', 'unknown_attribute'])
    assert affected['person_detect'] == ['lighting', 'occlusion']
    assert affected['person_track'] == ['occlusion']
    assert 'unknown_attribute' not in sum(affected.values(), [])
    # Lighting cannot affect a purely geometric zone rule.
    assert 'zone_intersect' not in affected
