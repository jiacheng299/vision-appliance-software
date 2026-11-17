"""Five-gate valid-observation decision and its three-state conclusion.

A window may only say "no event" when every gate was actually verified. A
conclusion of absence therefore demands strictly more evidence than a positive
detection: an unmeasured gate blocks absence but not detection.
"""
from dataclasses import dataclass

PASS = 'pass'
FAIL = 'fail'
UNVERIFIED = 'unverified'
NOT_APPLICABLE = 'not_applicable'

DETECTED = 'detected'
NOT_DETECTED = 'not_detected'
INSUFFICIENT = 'insufficient'

REASONS = {
    'frame_absent': '窗口内没有任何成功解码的帧。',
    'frame_rate_low': '实际帧率低于任务要求。',
    'frame_gap_large': '最大帧间隔超过任务允许窗口。',
    'window_short': '观察窗口短于任务要求。',
    'roi_not_visible': '监测区域可见比例不足。',
    'overexposed': '监测区域过曝比例超过门槛。',
    'blurred': '画面清晰度低于门槛。',
    'occluded': '监测区域遮挡比例超过门槛。',
    'target_too_small': '最小可辨目标尺度低于门槛。',
    'frame_unmapped': '帧时间无法映射到统一时钟。',
    'frame_time_discontinuous': '窗口内帧时间回退或不可用，观察不连续。',
    'path_incomplete': '执行路径未完整执行或输出协议不可解析。',
    'version_mismatch': '路由、画像或模型版本与当前不一致。',
    'unverified_scale': '目标尺度未测定，不足以支撑未检出结论。',
    'unverified_frame': '帧时间指标未测定，不足以支撑未检出结论。',
    'unverified_roi': '区域可见比例未测定，不足以支撑未检出结论。',
    'unverified_quality': '画面质量指标未测定，不足以支撑未检出结论。',
}


@dataclass(frozen=True)
class Gate:
    name: str
    status: str
    value: float | int | None = None
    threshold: float | int | None = None
    reason: str | None = None


def _minimum(name, value, threshold, fail_reason, missing_reason):
    if threshold is None:
        return Gate(name, NOT_APPLICABLE, value, None)
    if value is None:
        return Gate(name, UNVERIFIED, None, threshold, missing_reason)
    if value < threshold:
        return Gate(name, FAIL, value, threshold, fail_reason)
    return Gate(name, PASS, value, threshold)


def _maximum(name, value, threshold, fail_reason, missing_reason):
    if threshold is None:
        return Gate(name, NOT_APPLICABLE, value, None)
    if value is None:
        return Gate(name, UNVERIFIED, None, threshold, missing_reason)
    if value > threshold:
        return Gate(name, FAIL, value, threshold, fail_reason)
    return Gate(name, PASS, value, threshold)


def frame_time_gate(metrics, thresholds):
    if not metrics.frame_count:
        return (Gate('frame_count', FAIL, metrics.frame_count, None, 'frame_absent'),)
    if getattr(metrics, 'time_continuous', None) is False:
        return (Gate('time_continuous', FAIL, 0, 1, 'frame_time_discontinuous'),)
    gates = [_minimum('actual_fps', metrics.actual_fps, thresholds.min_fps,
                      'frame_rate_low', 'unverified_frame'),
             _maximum('max_gap_seconds', metrics.max_gap_seconds, thresholds.max_gap_seconds,
                      'frame_gap_large', 'unverified_frame'),
             _minimum('window_seconds', metrics.duration_seconds, thresholds.min_window_seconds,
                      'window_short', 'unverified_frame')]
    return tuple(gates)


def roi_gate(metrics, thresholds):
    return (_minimum('roi_visible_ratio', metrics.roi_visible_ratio,
                     thresholds.min_roi_visible_ratio, 'roi_not_visible', 'unverified_roi'),)


def quality_gate(metrics, thresholds):
    return (_maximum('overexposure_ratio', metrics.overexposure_ratio,
                     thresholds.max_overexposure_ratio, 'overexposed', 'unverified_quality'),
            _minimum('blur_score', metrics.blur_score, thresholds.min_blur_score,
                     'blurred', 'unverified_quality'),
            _maximum('occlusion_ratio', metrics.occlusion_ratio,
                     thresholds.max_occlusion_ratio, 'occluded', 'unverified_quality'),
            _minimum('target_scale_px', metrics.target_scale_px, thresholds.min_target_scale_px,
                     'target_too_small', 'unverified_scale'))


def path_gate(path_complete, nodes_completed=None):
    if not path_complete:
        return (Gate('path_complete', FAIL, 0, 1, 'path_incomplete'),)
    return (Gate('path_complete', PASS, 1, 1, None),)


def version_gate(versions, expected):
    if not expected:
        return (Gate('version_consistency', NOT_APPLICABLE),)
    mismatched = [key for key, value in expected.items()
                  if getattr(versions, key, None) != value]
    if mismatched:
        return (Gate('version_consistency', FAIL, None, None, 'version_mismatch'),)
    return (Gate('version_consistency', PASS, None, None, None),)


def evaluate(*, metrics, thresholds, detection_count, path_complete,
             versions, expected_versions=None, nodes_completed=None):
    """Return (verdict, gates). Detection is judged on verified windows as well."""
    gates = (frame_time_gate(metrics, thresholds) + roi_gate(metrics, thresholds)
             + quality_gate(metrics, thresholds) + path_gate(path_complete, nodes_completed)
             + version_gate(versions, expected_versions))
    failed = [gate for gate in gates if gate.status == FAIL]
    unverified = [gate for gate in gates if gate.status == UNVERIFIED]
    reasons = tuple(dict.fromkeys(gate.reason for gate in failed + unverified if gate.reason))
    if failed:
        return INSUFFICIENT, gates, tuple(REASONS.get(code, code) for code in reasons)
    if detection_count > 0:
        return DETECTED, gates, tuple(REASONS.get(code, code) for code in reasons)
    if unverified:
        return INSUFFICIENT, gates, tuple(REASONS.get(code, code) for code in reasons)
    return NOT_DETECTED, gates, ()


def conclusion_scope(verdict, window_start, window_end, roi):
    """Absence never leaves its own window and region."""
    if verdict != NOT_DETECTED:
        return None
    return {'window_start': window_start, 'window_end': window_end, 'roi': roi,
            'statement': '仅在本次窗口与监测区域内未检出，不外推到其他时段或区域。'}
