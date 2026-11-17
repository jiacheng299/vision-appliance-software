"""组合求解（M6）：可修复性过滤 + 式(2) 评分 + 预算约束。

    J(K) = C(K) + α·H(K) − β·X(K) − γ·R(K) − δ·S(K, K_old)

C 取每个需求上可达质量的最大值再按需求权重求和，避免堆叠同一任务的多个模型
虚增覆盖；H 在依赖链不完整时直接取 0，而不是给部分分；R 与 S 都先除以预算
再归一化，因此不同量纲可以相加。
"""
from dataclasses import dataclass

from . import capability as capability_table
from .graph import ALTERNATIVE, JOINT, SERIAL, TEMPORAL

DEFAULT_BUCKET = capability_table.DEFAULT_BUCKET
MIN_QUALITY = 0.60


@dataclass(frozen=True)
class Weights:
    alpha: float = 1.0
    beta: float = 0.2
    gamma: float = 0.3
    delta: float = 0.2

    def as_dict(self):
        return {'alpha': self.alpha, 'beta': self.beta, 'gamma': self.gamma,
                'delta': self.delta}


@dataclass(frozen=True)
class Budgets:
    cpu_ms: float = 200.0
    memory_mb: float = 1024.0
    transition_cpu_ms: float = 200.0

    def as_dict(self):
        return {'cpu_ms': self.cpu_ms, 'memory_mb': self.memory_mb,
                'transition_cpu_ms': self.transition_cpu_ms}


@dataclass(frozen=True)
class Combination:
    id: str
    label: str
    members: tuple[str, ...]


@dataclass(frozen=True)
class Evaluation:
    combination: Combination
    score: float | None
    coverage: float
    dependency: float
    conflict: float
    cost: float
    switch: float
    feasible: bool
    reasons: tuple[str, ...]
    bucket: str


def _get(table, capability_id):
    if table is None:
        return capability_table.get(capability_id)
    capability = table.get(capability_id)
    if capability is None:
        raise KeyError(f'未知模型能力：{capability_id}')
    return capability


def effective_bucket(combination, scenario, table=None):
    """Try to repair the observed scenario before judging model quality."""
    bucket = scenario.bucket
    if bucket == DEFAULT_BUCKET:
        return bucket
    for member in combination.members:
        capability = _get(table, member)
        if capability.kind == 'preprocess':
            bucket = capability.repaired_bucket(scenario)
            if bucket == DEFAULT_BUCKET:
                return bucket
    return bucket


def coverage(combination, graph, bucket, table=None):
    """C(K): best available quality per requirement, weighted by requirement weight."""
    total = sum(graph.requirement(key).weight for key in graph.keys)
    covered, missing = 0.0, []
    for key in graph.keys:
        best = 0.0
        for member in combination.members:
            capability = _get(table, member)
            if key in capability.provides:
                best = max(best, capability.quality_for(key, bucket))
        if best <= 0:
            missing.append(key)
        covered += graph.requirement(key).weight * best
    return (covered / total if total else 0.0), tuple(missing)


def dependency_satisfaction(combination, graph, table=None, chain_scores=None):
    """H(K): from the offline chain table when one exists, else all-or-nothing.

    The patent reads H from an offline calibration table of complete chains; an
    incomplete chain earns no partial credit, so the fallback is 0 or 1.
    """
    if chain_scores and combination.id in chain_scores:
        return float(chain_scores[combination.id])
    provided = set()
    for member in combination.members:
        provided.update(_get(table, member).provides)
    for edge in graph.dependencies():
        if edge.kind in (SERIAL, TEMPORAL, JOINT):
            if edge.source not in provided or edge.target not in provided:
                return 0.0
        elif edge.kind == ALTERNATIVE:
            if edge.source not in provided and edge.target not in provided:
                return 0.0
    return 1.0 if provided >= set(graph.keys) else 0.0


def conflict_degree(combination, table=None):
    """X(K): declared incompatibilities, normalised by the number of pairs."""
    members = list(combination.members)
    pairs = len(members) * (len(members) - 1) / 2
    if pairs <= 0:
        return 0.0
    hits = 0
    for index, member in enumerate(members):
        declared = set(_get(table, member).conflicts)
        for other in members[index + 1:]:
            if other in declared:
                hits += 1
    return min(1.0, hits / pairs)


def resource_totals(combination, table=None):
    cpu = sum(_get(table, member).cpu_ms for member in combination.members)
    memory = sum(_get(table, member).memory_mb for member in combination.members)
    return cpu, memory


def resource_cost(combination, budgets, table=None):
    """R(K): CPU milliseconds and resident memory, each divided by its budget."""
    cpu, memory = resource_totals(combination, table)
    cpu_ratio = cpu / budgets.cpu_ms if budgets.cpu_ms else 0.0
    memory_ratio = memory / budgets.memory_mb if budgets.memory_mb else 0.0
    return min(1.0, 0.5 * cpu_ratio + 0.5 * memory_ratio)


def switch_cost(combination, current, table=None):
    """S(K, K_old): share of members that have to be loaded or re-warmed."""
    if not current or not combination.members:
        return 0.0 if current is None else 1.0
    previous = set(current.members)
    if previous == set(combination.members):
        return 0.0
    new_members = set(combination.members) - previous
    return min(1.0, len(new_members) / len(combination.members))


def evaluate(combination, *, graph, scenario, weights=None, budgets=None, current=None,
             table=None, min_quality=MIN_QUALITY, chain_scores=None):
    """Hard filters first, then the score. Infeasible combinations get no score."""
    weights = weights or Weights()
    budgets = budgets or Budgets()
    bucket = effective_bucket(combination, scenario, table)
    covered, missing = coverage(combination, graph, bucket, table)
    dependency = dependency_satisfaction(combination, graph, table, chain_scores)
    conflict = conflict_degree(combination, table)
    cost = resource_cost(combination, budgets, table)
    switch = switch_cost(combination, current, table)
    reasons = []

    for member in combination.members:
        capability = _get(table, member)
        if not capability.installed:
            reasons.append(f'未安装：{capability.label}')
        if not capability.bucket_supported(bucket):
            reasons.append(f'不在适用场景分桶：{bucket}')
        if (scenario.target_px is not None and capability.min_target_px is not None
                and scenario.target_px < capability.min_target_px):
            reasons.append(f'目标尺度不足：{scenario.target_px:.0f} 像素'
                           f' < {capability.min_target_px:.0f} 像素')
    for key in missing:
        reasons.append(f'未覆盖需求：{key}')
    for key in graph.keys:
        if key in missing:
            continue
        best = max((_get(table, member).quality_for(key, bucket)
                    for member in combination.members if key in _get(table, member).provides),
                   default=0.0)
        if best < min_quality:
            reasons.append(f'低于必需质量：{key} {best:.2f} < {min_quality:.2f}')
    cpu, memory = resource_totals(combination, table)
    if cpu > budgets.cpu_ms:
        reasons.append(f'CPU 超出预算：{cpu:.0f} > {budgets.cpu_ms:.0f} 毫秒/帧')
    if memory > budgets.memory_mb:
        reasons.append(f'内存超出预算：{memory:.0f} > {budgets.memory_mb:.0f} MB')

    feasible = not reasons
    score = None
    if feasible:
        score = (covered + weights.alpha * dependency - weights.beta * conflict
                 - weights.gamma * cost - weights.delta * switch)
    return Evaluation(combination=combination, score=score, coverage=covered,
                      dependency=dependency, conflict=conflict, cost=cost,
                      switch=switch, feasible=feasible, reasons=tuple(reasons),
                      bucket=bucket)


def build_combinations(graph, table=None, *, include_uninstalled=True, max_members=4):
    """Enumerate every way to cover the requirements, plus optional preprocessors."""
    providers = {}
    for key in graph.keys:
        providers[key] = sorted(capability.id for capability in (table or capability_table.table()).values()
                                if key in capability.provides
                                and (include_uninstalled or capability.installed))
        if not providers[key]:
            raise ValueError(f'没有能力可以满足需求：{key}')
    prefixes = [capability.id for capability in (table or capability_table.table()).values()
                if capability.kind == 'preprocess'
                and (include_uninstalled or capability.installed)]
    results = []
    for choice in _product(providers):
        for count in range(0, min(len(prefixes), max_members - len(choice)) + 1):
            for extra in _choose(prefixes, count):
                members = tuple(sorted(set(choice) | set(extra)))
                if len(members) > max_members:
                    continue
                label = ' + '.join(_label(member, table) for member in members)
                results.append(Combination(id='combo:' + '+'.join(members), label=label,
                                           members=members))
    return results


def _label(capability_id, table=None):
    return _get(table, capability_id).label


def _product(providers):
    results = [()]
    for key, options in providers.items():
        results = [prefix + (option,) for prefix in results for option in options]
    return results


def _choose(items, count):
    if count == 0:
        return [()]
    if count > len(items):
        return []
    results = []
    for index, item in enumerate(items):
        for tail in _choose(items[index + 1:], count - 1):
            results.append((item,) + tail)
    return results


def solve(*, graph, scenario, weights=None, budgets=None, current=None, table=None,
          min_quality=MIN_QUALITY, candidates=None, chain_scores=None):
    """Exhaustive solve: the candidate space is small after feasibility filtering."""
    weights = weights or Weights()
    budgets = budgets or Budgets()
    combos = candidates if candidates is not None else build_combinations(graph, table)
    evaluations = [evaluate(combo, graph=graph, scenario=scenario, weights=weights,
                            budgets=budgets, current=current, table=table,
                            min_quality=min_quality, chain_scores=chain_scores)
                   for combo in combos]
    feasible = sorted((item for item in evaluations if item.feasible),
                      key=lambda item: (-item.score, len(item.combination.members),
                                        item.combination.id))
    blocked = sorted((item for item in evaluations if not item.feasible),
                     key=lambda item: item.combination.id)
    return Solution(chosen=feasible[0] if feasible else None, ranked=tuple(feasible),
                    blocked=tuple(blocked), weights=weights, budgets=budgets)


@dataclass(frozen=True)
class Solution:
    chosen: Evaluation | None
    ranked: tuple
    blocked: tuple
    weights: Weights
    budgets: Budgets

    def as_dict(self):
        return {'chosen': _evaluation_dict(self.chosen),
                'ranked': [_evaluation_dict(item) for item in self.ranked],
                'blocked': [_evaluation_dict(item) for item in self.blocked],
                'weights': self.weights.as_dict(), 'budgets': self.budgets.as_dict()}


def _evaluation_dict(item):
    if item is None:
        return None
    return {'combination_id': item.combination.id, 'label': item.combination.label,
            'members': list(item.combination.members), 'score': item.score,
            'coverage': item.coverage, 'dependency': item.dependency,
            'conflict': item.conflict, 'cost': item.cost, 'switch': item.switch,
            'feasible': item.feasible, 'reasons': list(item.reasons), 'bucket': item.bucket}
