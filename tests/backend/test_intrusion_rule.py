REGION = [[(0, 0), (1, 0), (1, 1), (0, 1)]]
PERSON = {'label': 'person', 'x': .4, 'y': .2, 'width': .2, 'height': .6, 'confidence': .9}


def rule():
    from app.modules.local_execution.intrusion import IntrusionRule
    return IntrusionRule(REGION, entry_seconds=8, occlusion_seconds=5, exit_seconds=10)


def test_startup_occupant_is_ignored_until_region_is_clear_then_entry_alarms_once():
    detector = rule()
    assert detector.observe(0, [PERSON]).phase == 'waiting_clear'
    assert detector.observe(5, [PERSON]).alarm is False
    assert detector.observe(6, []).phase == 'waiting_clear'
    assert detector.observe(15.9, []).phase == 'waiting_clear'
    assert detector.observe(16, []).phase == 'armed'

    first = detector.observe(20, [PERSON])
    track_id = first.targets[0].id
    assert first.phase == 'confirming' and first.confirmed_seconds == 0
    for timestamp in range(21, 28):
        assert detector.observe(timestamp, [PERSON]).alarm is False
    alarm = detector.observe(28, [PERSON])
    assert alarm.alarm is True and alarm.phase == 'alarmed'
    assert alarm.track_id == track_id and alarm.confirmed_seconds == 8
    assert detector.observe(40, [PERSON]).alarm is False


def test_short_occlusion_pauses_confirmation_and_long_occlusion_resets_candidate():
    detector = rule()
    detector.observe(0, [])
    detector.observe(10, [])
    first = detector.observe(11, [PERSON])
    detector.observe(12, [PERSON])
    detector.observe(13, [PERSON])
    assert detector.observe(14, []).confirmed_seconds == 2
    assert detector.observe(18, []).phase == 'occluded'
    resumed = detector.observe(18.5, [PERSON])
    assert resumed.targets[0].id == first.targets[0].id
    assert resumed.confirmed_seconds == 2
    assert detector.observe(19.5, [PERSON]).confirmed_seconds == 3

    detector.observe(20, [])
    assert detector.observe(25.1, []).phase == 'armed'
    restarted = detector.observe(26, [PERSON])
    assert restarted.confirmed_seconds == 0


def test_alarmed_episode_ends_after_ten_clear_seconds_and_disconnect_requires_rearming():
    detector = rule()
    detector.observe(0, [])
    detector.observe(10, [])
    detector.observe(11, [PERSON])
    for timestamp in range(12, 20):
        observation = detector.observe(timestamp, [PERSON])
    assert observation.alarm is True
    assert detector.observe(20, []).phase == 'alarmed'
    assert detector.observe(29.9, []).phase == 'alarmed'
    assert detector.observe(30, []).phase == 'armed'

    detector.mark_unavailable()
    assert detector.observe(31, [PERSON]).phase == 'waiting_clear'
    detector.observe(40, [])
    assert detector.observe(50, []).phase == 'armed'


def test_invalid_time_and_non_person_boxes_are_rejected_or_ignored():
    import pytest
    detector = rule()
    detector.observe(0, [])
    with pytest.raises(ValueError):
        detector.observe(-1, [])
    detector = rule()
    detector.observe(0, [])
    detector.observe(10, [])
    result = detector.observe(11, [{'label': 'car', 'x': .4, 'y': .2, 'width': .2, 'height': .6}])
    assert result.count == 0 and result.phase == 'armed'


def test_long_gap_without_decoded_observations_does_not_confirm_or_preserve_identity():
    detector = rule()
    detector.observe(0, [])
    detector.observe(10, [])
    first = detector.observe(11, [PERSON])
    resumed = detector.observe(20, [PERSON])
    assert resumed.confirmed_seconds == 0
    assert resumed.targets[0].id != first.targets[0].id
