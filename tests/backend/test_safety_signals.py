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
