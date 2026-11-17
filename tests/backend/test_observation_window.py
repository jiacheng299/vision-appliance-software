"""观察窗口聚合：只有真正闭合、且时间连续的窗口才能产出结论。"""
import pytest

from app.modules.semantics.metrics import FrameMetrics
from app.modules.semantics.window import ObservationWindow


def measurement(brightness=.5, overexposure=.0, blur=100.0, roi=1.0):
    return FrameMetrics(width=8, height=8, brightness=brightness, overexposure_ratio=overexposure,
                        roi_visible_ratio=roi, blur_score=blur)


def feed(window, start, count, step=1.0):
    for index in range(count):
        window.add_frame(start + index * step)


def test_window_opens_on_the_first_frame_and_closes_after_its_length():
    window = ObservationWindow(10.0)
    assert window.due(0.0) is False
    window.add_frame(0.0)
    assert window.due(9.9) is False
    assert window.due(10.0) is True
    assert window.metrics()['frame_count'] == 1


def test_frame_rate_and_largest_gap_come_from_the_frames_actually_read():
    window = ObservationWindow(10.0)
    feed(window, 0.0, 5)          # 0..4, one second apart
    window.add_frame(9.0)         # a five second transport gap
    metrics = window.metrics()
    assert metrics['frame_count'] == 6
    assert metrics['max_gap_seconds'] == 5.0
    assert metrics['duration_seconds'] == 9.0
    assert metrics['actual_fps'] == pytest.approx(6 / 9.0)


def test_backward_timestamp_invalidates_the_window_instead_of_being_dropped():
    window = ObservationWindow(10.0)
    window.add_frame(5.0)
    window.add_frame(3.0)
    metrics = window.metrics()
    assert metrics['time_continuous'] is False
    assert metrics['duration_seconds'] is None
    assert metrics['actual_fps'] is None


def test_worst_case_wins_across_the_samples_of_one_window():
    window = ObservationWindow(10.0)
    feed(window, 0.0, 3)
    window.add_sample(measurement(overexposure=.05, blur=200.0, roi=1.0), detection_count=1,
                      target_scale=40.0)
    window.add_sample(measurement(overexposure=.4, blur=80.0, roi=.8), detection_count=0,
                      target_scale=None)
    metrics = window.metrics()
    assert metrics['overexposure_ratio'] == .4      # maximum
    assert metrics['blur_score'] == 80.0            # minimum
    assert metrics['roi_visible_ratio'] == .8       # minimum
    assert metrics['target_scale_px'] == 40.0       # best observed target
    assert window.detections == 1                   # any hit in the window counts


def test_unmeasured_values_stay_unmeasured_and_occlusion_is_never_invented():
    window = ObservationWindow(10.0)
    feed(window, 0.0, 2)
    window.add_sample(FrameMetrics(width=8, height=8, brightness=None, overexposure_ratio=None,
                                   roi_visible_ratio=None, blur_score=None))
    metrics = window.metrics()
    assert metrics['overexposure_ratio'] is None
    assert metrics['blur_score'] is None
    assert metrics['roi_visible_ratio'] is None
    assert metrics['occlusion_ratio'] is None


def test_reset_keeps_the_length_and_clears_every_accumulated_evidence():
    window = ObservationWindow(10.0)
    feed(window, 0.0, 4)
    window.add_sample(measurement(overexposure=.3), detection_count=2, target_scale=30.0)
    window.reset(4.0)
    assert window.seconds == 10.0
    assert (window.frames, window.samples, window.detections) == (0, 0, 0)
    assert window.overexposure is None and window.target_scale is None
    assert window.continuous is True
    assert window.started_at == 4.0


def test_window_without_samples_is_not_usable():
    window = ObservationWindow(10.0)
    feed(window, 0.0, 3)
    assert window.usable is False
    window.add_sample(measurement())
    assert window.usable is True
