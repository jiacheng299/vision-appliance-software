"""组合求解（M6）：式(2) 评分、硬约束过滤与可修复性判定。"""
import copy
from dataclasses import replace

import pytest

from app.modules.routing import capability as capabilities
from app.modules.routing import graph as graphs
from app.modules.routing import solver
from app.modules.routing.capability import Capability, Scenario


def capability(**kwargs):
    base = dict(kind='detect', target='person', label=kwargs['id'], installed=True,
                calibrated=False, provides=(), quality={}, cpu_ms=0.0, memory_mb=0.0)
    base.update(kwargs)
    return dict(base)


def patent_table():
    """交底书实施例一的三个候选组合，数值取自该实施例的离线能力示例表。"""
    return {
        'generic-detect': Capability(**capability(id='generic-detect', provides=('person',),
                                                  quality={'person': .72}, cpu_ms=320., memory_mb=80.)),
        'generic-track': Capability(**capability(id='generic-track', kind='event',
                                                 provides=('zone',), quality={'zone': .65})),
        'snow-detect': Capability(**capability(id='snow-detect', provides=('person',),
                                               quality={'person': .90}, cpu_ms=628., memory_mb=60.)),
        'snow-track': Capability(**capability(id='snow-track', kind='event',
                                              provides=('zone',), quality={'zone': .88})),
        'de-lare': Capability(**capability(id='de-lare', kind='preprocess', installed=True,
                                           repairs={'glare': 'default'}, cpu_ms=12., memory_mb=0.,
                                           unrecoverable_saturation=.08)),
        'multi-task': Capability(**capability(id='multi-task', provides=('person', 'zone'),
                                              quality={'person': .78, 'zone': .76},
                                              cpu_ms=240., memory_mb=60.)),
    }


PATENT_GRAPH = graphs.RequirementGraph(
    [graphs.Requirement('person', 'detect', 'person', 0.5),
     graphs.Requirement('zone', 'event', 'person', 0.5)],
    [graphs.Edge('person', 'zone', graphs.SERIAL)])

PATENT_CANDIDATES = [
    solver.Combination(id='combo-generic', label='通用检测+通用跟踪',
                       members=('generic-detect', 'generic-track')),
    solver.Combination(id='combo-snow', label='雪地检测+跟踪+去眩光',
                       members=('de-lare', 'snow-detect', 'snow-track')),
    solver.Combination(id='combo-multi', label='通用多任务模型', members=('multi-task',)),
]
# 离线链路标定表里的依赖满足量 H(K)；交底书示例为 0.05 / 0.12 / 0。
PATENT_CHAINS = {'combo-generic': .05, 'combo-snow': .12, 'combo-multi': 0.0}


def patent_solve(min_quality):
    return solver.solve(graph=PATENT_GRAPH, scenario=Scenario(), table=patent_table(),
                        budgets=solver.Budgets(cpu_ms=1000., memory_mb=1000.),
                        candidates=PATENT_CANDIDATES, chain_scores=PATENT_CHAINS,
                        min_quality=min_quality)


def test_scores_reproduce_the_worked_example_in_the_patent():
    solution = patent_solve(min_quality=0.0)
    scores = {item.combination.id: item.score for item in solution.ranked}
    assert scores['combo-generic'] == pytest.approx(0.675, abs=1e-9)
    assert scores['combo-snow'] == pytest.approx(0.905, abs=1e-9)
    assert scores['combo-multi'] == pytest.approx(0.725, abs=1e-9)
    assert solution.chosen.combination.id == 'combo-snow'


def test_a_hard_quality_floor_leaves_only_the_snow_combination():
    solution = patent_solve(min_quality=0.80)
    assert solution.chosen.combination.id == 'combo-snow'
    blocked = {item.combination.id: item.reasons for item in solution.blocked}
    assert 'combo-generic' in blocked and 'combo-multi' in blocked
    assert any('低于必需质量' in reason for reason in blocked['combo-multi'])


def test_coverage_takes_the_best_member_per_requirement_not_the_sum():
    covered, missing = solver.coverage(
        solver.Combination(id='x', label='x', members=('generic-detect', 'snow-detect')),
        PATENT_GRAPH, 'default', patent_table())
    # person = max(.72, .90) = .90; zone missing -> 0; weights 0.5/0.5
    assert covered == pytest.approx(0.45)
    assert missing == ('zone',)


def test_dependency_satisfaction_is_all_or_nothing_without_a_chain_table():
    half = solver.dependency_satisfaction(
        solver.Combination(id='x', label='x', members=('generic-detect',)), PATENT_GRAPH,
        patent_table())
    full = solver.dependency_satisfaction(
        solver.Combination(id='y', label='y', members=('generic-detect', 'generic-track')),
        PATENT_GRAPH, patent_table())
    assert half == 0.0 and full == 1.0


def test_switch_cost_counts_only_the_members_that_must_be_loaded():
    table = patent_table()
    current = solver.Combination(id='current', label='当前', members=('generic-detect', 'generic-track'))
    same = solver.switch_cost(current, current, table)
    partial = solver.switch_cost(
        solver.Combination(id='next', label='next', members=('generic-detect', 'snow-track')),
        current, table)
    assert same == 0.0
    assert partial == pytest.approx(0.5)


def test_seed_table_chooses_the_only_installed_detector_under_clear_conditions():
    solution = solver.solve(graph=graphs.build('absence'), scenario=Scenario())
    assert solution.chosen is not None
    assert solution.chosen.combination.members == ('yolo11n-person',)
    assert solution.chosen.coverage == pytest.approx(0.72)


def test_glare_without_the_repair_capability_has_no_feasible_route():
    scenario = Scenario(bucket='glare', reasons=('场景分桶：glare',))
    solution = solver.solve(graph=graphs.build('absence'), scenario=scenario)
    assert solution.chosen is None
    reasons = [reason for item in solution.blocked for reason in item.reasons]
    assert any('低于必需质量' in reason for reason in reasons)
    assert any('未安装' in reason for reason in reasons)


def test_repair_is_effective_only_below_the_unrecoverable_saturation_limit():
    installed = {**capabilities.table(),
                 'glare-removal': replace(capabilities.get('glare-removal'), installed=True)}
    recoverable = solver.solve(graph=graphs.build('absence'),
                               scenario=Scenario(bucket='glare', saturated_ratio=.02),
                               table=installed)
    assert recoverable.chosen is not None
    assert 'glare-removal' in recoverable.chosen.combination.members
    assert recoverable.chosen.bucket == 'default'

    lost = solver.solve(graph=graphs.build('absence'),
                        scenario=Scenario(bucket='glare', saturated_ratio=.5), table=installed)
    assert lost.chosen is None
    assert any('低于必需质量' in reason for item in lost.blocked for reason in item.reasons)


def test_resource_budget_rejects_combinations_that_cannot_run_here():
    solution = solver.solve(graph=graphs.build('absence'), scenario=Scenario(),
                            budgets=solver.Budgets(cpu_ms=10., memory_mb=10.))
    assert solution.chosen is None
    assert any('超出预算' in reason for item in solution.blocked for reason in item.reasons)


def test_target_scale_below_the_model_minimum_is_refused():
    solution = solver.solve(graph=graphs.build('absence'),
                            scenario=Scenario(target_px=12.0))
    assert solution.chosen is None
    assert any('目标尺度不足' in reason for item in solution.blocked for reason in item.reasons)


def test_intrusion_needs_the_whole_chain_and_scores_dependency():
    solution = solver.solve(graph=graphs.build('intrusion', duration_seconds=8.0),
                            scenario=Scenario())
    assert solution.chosen is not None
    assert set(solution.chosen.combination.members) == {'yolo11n-person', 'heuristic-tracker',
                                                        'zone-rule'}
    assert solution.chosen.dependency == 1.0
    assert solution.chosen.coverage == pytest.approx(0.5 * 0.72 + 0.3 * 0.65 + 0.2 * 0.90)


def test_candidate_enumeration_covers_every_installed_and_declared_option():
    combos = solver.build_combinations(graphs.build('absence'))
    ids = {combo.id for combo in combos}
    # two detectors x (no preprocessor, each of two preprocessors, both)
    assert len(ids) == 8
    assert 'combo:yolo11n-person' in ids
    assert 'combo:center-crop+glare-removal+yolo11n-person' in ids


def test_greedy_and_exhaustive_agree_on_the_seed_table():
    solution = solver.solve(graph=graphs.build('absence'), scenario=Scenario())
    best = max((item for item in solution.ranked), key=lambda item: item.score)
    assert best.combination.id == solution.chosen.combination.id
