"""式(3) 滞回与切换门禁（S13）。

    进入候选：ΔJ ≥ ε_in ；取消候选：ΔJ ≤ −ε_out

滞回只负责抑制抖动，不负责拖延已经失效的硬条件：当前组合失去硬可行性时
绕过收益等待，但仍然要求候选取得一个有效观察窗口后才接管结果。
"""
from dataclasses import dataclass

STABLE = 'stable'
CANDIDATE = 'candidate'

HOLD = 'hold'
ENTER = 'enter'
CANCEL = 'cancel'
SWITCH = 'switch'

STATE_MODES = (STABLE, CANDIDATE)
ACTIONS = (HOLD, ENTER, CANCEL, SWITCH)


@dataclass(frozen=True)
class Thresholds:
    epsilon_in: float = 0.06
    epsilon_out: float = 0.06
    min_dwell_seconds: float = 120.0
    required_windows: int = 2

    def as_dict(self):
        return {'epsilon_in': self.epsilon_in, 'epsilon_out': self.epsilon_out,
                'min_dwell_seconds': self.min_dwell_seconds,
                'required_windows': self.required_windows}


@dataclass(frozen=True)
class State:
    mode: str = STABLE
    active_since: float | None = None
    candidate_since: float | None = None
    valid_windows: int = 0
    hard_failure: bool = False

    def as_dict(self):
        return {'mode': self.mode, 'active_since': self.active_since,
                'candidate_since': self.candidate_since,
                'valid_windows': self.valid_windows,
                'hard_failure': self.hard_failure}


@dataclass(frozen=True)
class Decision:
    action: str
    state: State
    reason: str


def required_windows(state, thresholds):
    """A candidate admitted because the active set broke needs only one window."""
    return 1 if state.hard_failure else thresholds.required_windows


def decide(*, state, delta_j, now, elapsed=None, thresholds=None, hard_infeasible=False,
           window_valid=False):
    """One hysteresis step. `elapsed` is how long the active combination has run."""
    thresholds = thresholds or Thresholds()
    if state.mode not in STATE_MODES:
        raise ValueError(f'未知滞回状态：{state.mode}')

    if hard_infeasible and state.mode == STABLE:
        return Decision(ENTER, State(mode=CANDIDATE, active_since=state.active_since,
                                     candidate_since=now, valid_windows=1 if window_valid else 0,
                                     hard_failure=True),
                        '当前组合已失去硬可行性，绕过收益等待进入候选验证')

    if state.mode == CANDIDATE:
        if delta_j is not None and delta_j <= -thresholds.epsilon_out:
            return Decision(CANCEL, State(mode=STABLE, active_since=state.active_since),
                            f'评分增益回落到取消阈值以下（当前评分增益 {delta_j:.3f} ≤ '
                            f'取消阈值 −{thresholds.epsilon_out:.3f}）')
        windows = state.valid_windows + (1 if window_valid else 0)
        required = required_windows(state, thresholds)
        if windows >= required:
            return Decision(SWITCH, State(mode=STABLE, active_since=now), 
                            f'候选已取得 {windows} 个有效观察窗口，满足切换要求')
        return Decision(HOLD, State(mode=CANDIDATE, active_since=state.active_since,
                                    candidate_since=state.candidate_since,
                                    valid_windows=windows, hard_failure=state.hard_failure),
                        f'候选继续验证（{windows}/{required} 个有效窗口）')

    if delta_j is None:
        return Decision(HOLD, state, '没有可比较的候选评分')
    if elapsed is not None and elapsed < thresholds.min_dwell_seconds:
        return Decision(HOLD, state,
                        f'当前组合仍处于最短驻留时间（{elapsed:.0f}/'
                        f'{thresholds.min_dwell_seconds:.0f} 秒）')
    if delta_j >= thresholds.epsilon_in:
        return Decision(ENTER, State(mode=CANDIDATE, active_since=state.active_since,
                                     candidate_since=now, valid_windows=1 if window_valid else 0),
                        f'评分增益达到进入阈值（当前评分增益 {delta_j:.3f} ≥ '
                        f'进入阈值 {thresholds.epsilon_in:.3f}）')
    return Decision(HOLD, state, f'评分增益未达到进入阈值（当前评分增益 {delta_j:.3f}）')
