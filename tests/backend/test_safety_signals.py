from app.modules.local_execution.safety_signals import ObservationWindow, SafetySignal


def test_reports_gaps_and_nonincreasing_timestamps():
    window = ObservationWindow(max_gap_seconds=3)
    assert window.check_time(0) is None
    assert window.check_time(3) is None
    assert window.check_time(7) == SafetySignal('sample_gap', 3, 7)
    assert window.check_time(7) == SafetySignal('sample_time_not_increasing', 7, 7)
    assert window.check_time(2) == SafetySignal('sample_time_not_increasing', 2, 7)
    assert window.check_time(3) is None


def test_invalid_time_and_new_stream_reset_the_window():
    window = ObservationWindow(max_gap_seconds=3)
    window.check_time(20)
    assert window.check_time(float('nan')) == SafetySignal('invalid_sample_time')
    assert window.check_time(1) is None
    window.reset()
    assert window.check_time(0) is None


def test_requires_repeated_changes_and_weak_support():
    weak = ObservationWindow(max_gap_seconds=2)
    confident = ObservationWindow(max_gap_seconds=2)
    signals = []
    for timestamp, present in enumerate((True, False, True, False)):
        assert weak.check_time(timestamp) is None
        assert confident.check_time(timestamp) is None
        signals.append(weak.check_detection(timestamp, present, weak_support=present))
        assert confident.check_detection(timestamp, present, weak_support=False) is None
    assert signals == [None, None, None, SafetySignal('unstable_detection', 0, 3)]


def test_gaps_and_aged_samples_do_not_accumulate_detection_risk():
    window = ObservationWindow(max_gap_seconds=2)
    for timestamp, present in enumerate((True, False, True)):
        window.check_time(timestamp)
        assert window.check_detection(timestamp, present, weak_support=present) is None
    assert window.check_time(10) == SafetySignal('sample_gap', 2, 10)
    assert window.check_detection(10, False, weak_support=False) is None
    for timestamp in range(11, 32):
        window.check_time(timestamp)
        assert window.check_detection(timestamp, True, weak_support=True) is None
    window.check_time(32)
    assert window.check_detection(32, False, weak_support=False) is None
