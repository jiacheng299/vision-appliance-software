"""候选组合预热的资源实测（对应交底书 S14 的影子运行成本）。

本机只有一份可信 ONNX，因此这里测量的是「同时保持两个推理会话」的代价：
会话加载时间、常驻内存增量、单帧推理延迟增量。它不能证明"另一个模型更强"，
只能回答"影子运行要额外吃掉多少资源"——这正是过渡预算需要的数字。
"""
from dataclasses import asdict, dataclass
import time

DEFAULT_FRAMES = 5
WARMUP_FRAMES = 2


@dataclass(frozen=True)
class PreheatMeasurement:
    available: bool
    reason: str | None
    model_path: str | None
    frames: int
    load_ms: float | None = None
    baseline_ms: float | None = None
    shadow_ms: float | None = None
    latency_delta_ms: float | None = None
    rss_before_mb: float | None = None
    rss_first_mb: float | None = None
    rss_after_mb: float | None = None
    # 第二个会话的边际内存，才是个体预算要看的数字
    rss_delta_mb: float | None = None
    # 两个会话相对空闲进程的总增量，用于判断整机是否吃得下
    rss_total_mb: float | None = None
    notes: tuple = ()

    def as_dict(self):
        payload = asdict(self)
        payload['notes'] = list(self.notes)
        return payload


def _rss_mb(psutil):
    return psutil.Process().memory_info().rss / (1024 * 1024)


def _blank_time(session, feed_name, tensor, frames):
    started = time.perf_counter()
    for _ in range(frames):
        session.run(None, {feed_name: tensor})
    return (time.perf_counter() - started) * 1000.0 / frames


def _one_frame(session, feed_name, tensor):
    started = time.perf_counter()
    session.run(None, {feed_name: tensor})
    return (time.perf_counter() - started) * 1000.0


def _median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def measure(model_path, *, frames=DEFAULT_FRAMES, size=(640, 640)):
    """Load two sessions of the same artifact and report the marginal cost."""
    frames = max(1, int(frames))
    notes = ['两次加载的是同一份 ONNX：本机只有一种检测能力，',
             '这里测量的是并存代价，不是模型能力差异。']
    try:
        import numpy as np
        import onnxruntime as ort
        import psutil
    except ImportError as error:
        return PreheatMeasurement(False, f'缺少测量依赖：{error}', str(model_path), frames,
                                  notes=tuple(notes))
    try:
        path = str(model_path)
        with open(path, 'rb') as handle:
            if not handle.read(4):
                raise OSError('模型文件为空')
    except OSError as error:
        return PreheatMeasurement(False, f'模型文件不可读：{error}', str(model_path), frames,
                                  notes=tuple(notes))

    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    tensor = np.zeros((1, 3, size[1], size[0]), dtype=np.float32)
    try:
        rss_before = _rss_mb(psutil)
        started = time.perf_counter()
        baseline = ort.InferenceSession(path, sess_options=options,
                                        providers=['CPUExecutionProvider'])
        load_ms = (time.perf_counter() - started) * 1000.0
        feed = baseline.get_inputs()[0].name
        for _ in range(WARMUP_FRAMES):
            baseline.run(None, {feed: tensor})
        rss_middle = _rss_mb(psutil)
        started = time.perf_counter()
        shadow = ort.InferenceSession(path, sess_options=options,
                                      providers=['CPUExecutionProvider'])
        shadow_load_ms = (time.perf_counter() - started) * 1000.0
        shadow_feed = shadow.get_inputs()[0].name
        for _ in range(WARMUP_FRAMES):
            shadow.run(None, {shadow_feed: tensor})
        # 交替计时，避免机器负载漂移被算到某一个会话头上
        baseline_times, shadow_times = [], []
        for _ in range(frames):
            baseline_times.append(_one_frame(baseline, feed, tensor))
            shadow_times.append(_one_frame(shadow, shadow_feed, tensor))
        baseline_ms, shadow_ms = _median(baseline_times), _median(shadow_times)
        rss_after = _rss_mb(psutil)
    except Exception as error:  # onnxruntime 的失败类型很杂，统一如实报告
        return PreheatMeasurement(False, f'会话加载或推理失败：{error}', str(model_path), frames,
                                  notes=tuple(notes))
    notes.append(f'第二个会话额外加载 {shadow_load_ms:.0f} 毫秒。')
    notes.append('rss_delta_mb 是第二个会话的边际内存；rss_total_mb 是两个会话的总增量。')
    return PreheatMeasurement(
        available=True, reason=None, model_path=path, frames=frames,
        load_ms=round(load_ms, 1), baseline_ms=round(baseline_ms, 2),
        shadow_ms=round(shadow_ms, 2), latency_delta_ms=round(shadow_ms - baseline_ms, 2),
        rss_before_mb=round(rss_before, 1), rss_first_mb=round(rss_middle, 1),
        rss_after_mb=round(rss_after, 1),
        rss_delta_mb=round(rss_after - rss_middle, 1),
        rss_total_mb=round(rss_after - rss_before, 1), notes=tuple(notes))


def budget_check(measurement, *, budgets_cpu_ms, budgets_memory_mb):
    """把实测结果换算成过渡预算是否够用，供式(2) 的资源项参考。"""
    if not measurement.available:
        return {'fits': None, 'reason': measurement.reason}
    fits_memory = measurement.rss_delta_mb is not None and measurement.rss_delta_mb <= budgets_memory_mb
    fits_cpu = measurement.shadow_ms is not None and measurement.shadow_ms <= budgets_cpu_ms
    reasons = []
    if not fits_memory:
        reasons.append(f'内存增量 {measurement.rss_delta_mb} MB 超出预算 {budgets_memory_mb} MB')
    if not fits_cpu:
        reasons.append(f'单帧耗时 {measurement.shadow_ms} ms 超出预算 {budgets_cpu_ms} ms')
    return {'fits': fits_memory and fits_cpu, 'reason': '；'.join(reasons) or '过渡预算可容纳'}
