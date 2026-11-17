"""五道门禁与三态结论：未检出比"检测到"要求更完整的证据。"""
import pytest

from app.modules.semantics import observe
from app.modules.semantics.schemas import ObservationMetrics, ObservationThresholds, Versions

THRESHOLDS = ObservationThresholds(min_fps=0.9, max_gap_seconds=1.5, min_window_seconds=20.0,
                                   min_roi_visible_ratio=0.9, max_overexposure_ratio=0.2,
                                   min_blur_score=50.0, max_occlusion_ratio=0.3,
                                   min_target_scale_px=24.0)
CURRENT = Versions(route_version='route-7', profile_version=3, model_version='yolo11n-1')


def metrics(**overrides):
    base = dict(frame_count=30, duration_seconds=30.0, actual_fps=1.0, max_gap_seconds=1.1,
                brightness=0.5, roi_visible_ratio=1.0, overexposure_ratio=0.05, blur_score=120.0,
                occlusion_ratio=0.0, target_scale_px=40.0)
    base.update(overrides)
    return ObservationMetrics(**base)


def verdict(count=0, measured=None, path_complete=True, versions=None, expected=None):
    return observe.evaluate(metrics=measured or metrics(), thresholds=THRESHOLDS,
                            detection_count=count, path_complete=path_complete,
                            versions=versions or CURRENT,
                            expected_versions=expected if expected is not None else CURRENT.model_dump())


def reasons_of(result):
    return ' '.join(result[2])


def test_verified_empty_window_is_not_detected_inside_its_own_scope():
    state, gates, messages = verdict(count=0)
    assert state == observe.NOT_DETECTED
    assert messages == ()
    assert all(gate.status in (observe.PASS, observe.NOT_APPLICABLE) for gate in gates)
    scope = observe.conclusion_scope(state, 10.0, 40.0, [[0, 0], [1, 0], [1, 1], [0, 1]])
    assert scope['window_start'] == 10.0 and scope['window_end'] == 40.0


def test_verified_hit_is_detected_even_when_absence_only_gates_are_unmeasured():
    state, _, _ = verdict(count=2, measured=metrics(target_scale_px=None))
    assert state == observe.DETECTED


def test_overexposed_region_never_becomes_absence_evidence():
    state, gates, messages = verdict(count=0, measured=metrics(overexposure_ratio=0.55))
    assert state == observe.INSUFFICIENT
    assert '过曝' in reasons_of((state, gates, messages))
    assert observe.conclusion_scope(state, 0.0, 1.0, []) is None


def test_unmeasured_quality_blocks_absence_but_not_detection():
    blurred_unknown = metrics(blur_score=None)
    empty_state, _, empty_messages = verdict(count=0, measured=blurred_unknown)
    assert empty_state == observe.INSUFFICIENT
    assert '画面质量指标未测定' in ' '.join(empty_messages)
    hit_state, _, _ = verdict(count=1, measured=blurred_unknown)
    assert hit_state == observe.DETECTED


def test_missing_frames_cannot_produce_any_conclusion():
    state, _, messages = verdict(count=0, measured=metrics(frame_count=0, actual_fps=0.0))
    assert state == observe.INSUFFICIENT
    assert '没有任何成功解码的帧' in ' '.join(messages)


def test_frame_gap_beyond_the_window_invalidates_the_observation():
    state, _, messages = verdict(count=0, measured=metrics(max_gap_seconds=4.0))
    assert state == observe.INSUFFICIENT
    assert '最大帧间隔' in ' '.join(messages)


def test_incomplete_path_or_stale_version_invalidates_the_window():
    torn, _, torn_messages = verdict(count=1, path_complete=False)
    assert torn == observe.INSUFFICIENT
    assert '执行路径' in ' '.join(torn_messages)
    stale, _, stale_messages = verdict(count=1, versions=Versions(route_version='route-6',
                                                                 profile_version=3,
                                                                 model_version='yolo11n-1'))
    assert stale == observe.INSUFFICIENT
    assert '版本' in ' '.join(stale_messages)


def test_partially_visible_region_is_reported_as_insufficient():
    state, _, messages = verdict(count=0, measured=metrics(roi_visible_ratio=0.4))
    assert state == observe.INSUFFICIENT
    assert '可见比例不足' in ' '.join(messages)


def test_occlusion_measured_elsewhere_still_gates_absence():
    state, _, messages = verdict(count=0, measured=metrics(occlusion_ratio=0.8))
    assert state == observe.INSUFFICIENT
    assert '遮挡比例' in ' '.join(messages)


@pytest.mark.parametrize('field,value,expected_reason', [
    ('actual_fps', 0.2, '实际帧率'),
    ('duration_seconds', 5.0, '观察窗口短于'),
    ('blur_score', 10.0, '清晰度'),
    ('target_scale_px', 12.0, '可辨目标尺度'),
])
def test_each_quality_gate_alone_is_enough_to_withhold_absence(field, value, expected_reason):
    state, _, messages = verdict(count=0, measured=metrics(**{field: value}))
    assert state == observe.INSUFFICIENT
    assert expected_reason in ' '.join(messages)


def test_protocol_valid_empty_detection_set_is_a_legitimate_output():
    # A detection node that ran correctly and returned nothing is not an error.
    state, gates, _ = verdict(count=0, path_complete=True, measured=metrics())
    assert state == observe.NOT_DETECTED
    assert [gate.status for gate in gates if gate.name == 'path_complete'] == [observe.PASS]
