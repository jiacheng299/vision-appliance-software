import pytest

REGIONS=[[(0,0),(1,0),(1,1),(0,1)]]
PERSON={'label':'person','x':.2,'y':.2,'width':.2,'height':.5,'confidence':.9}


def test_visible_targets_match_people_counted_inside_roi():
    from app.modules.local_execution.presence import PresenceRule
    detector=PresenceRule([[(0,0),(.5,0),(.5,1),(0,1)]])
    outside={**PERSON,'x':.7}
    nonperson={**PERSON,'label':'car'}
    boxes=[PERSON,outside,nonperson]
    assert detector.targets_in_regions(boxes)==[PERSON]
    assert detector.observe(0,boxes).count==1

def rule(**kwargs):
    from app.modules.local_execution.presence import PresenceRule
    return PresenceRule(REGIONS,**kwargs)

def test_absence_and_recovery_each_require_the_full_duration():
    detector=rule(duration_seconds=3)
    assert detector.observe(0,[]).transition is None
    assert detector.observe(3,[]).transition=='absence'
    assert detector.observe(3,[]).alarm is False
    assert detector.observe(4,[PERSON]).present_seconds==0
    assert detector.observe(6,[PERSON]).transition is None
    restored=detector.observe(7,[PERSON])
    assert restored.transition=='restored'
    assert restored.state=='normal'
    assert restored.alarm is False

def test_second_complete_absence_and_recovery_cycle_transitions_once_each():
    detector=rule(duration_seconds=2)
    assert detector.observe(0,[]).transition is None
    assert detector.observe(2,[]).transition=='absence'
    assert detector.observe(3,[PERSON]).transition is None
    assert detector.observe(5,[PERSON]).transition=='restored'
    assert detector.observe(6,[]).transition is None
    second_absence=detector.observe(8,[])
    assert second_absence.state=='absence'
    assert second_absence.transition=='absence'
    assert second_absence.alarm is True
    assert detector.observe(9,[PERSON]).transition is None
    second_restoration=detector.observe(11,[PERSON])
    assert second_restoration.state=='normal'
    assert second_restoration.transition=='restored'

def test_brief_presence_does_not_clear_confirmed_absence():
    detector=rule(duration_seconds=2)
    detector.observe(0,[])
    detector.observe(2,[])
    detector.observe(3,[PERSON])
    interrupted=detector.observe(4,[])
    assert interrupted.state=='absence'
    assert interrupted.present_seconds==0
    assert interrupted.transition is None

def test_unavailable_observation_preserves_alarm_but_resets_recovery_evidence():
    detector=rule(duration_seconds=2,alarm_interval_seconds=30)
    detector.observe(0,[])
    confirmed=detector.observe(2,[])
    assert confirmed.alarm is True
    detector.observe(3,[PERSON])
    detector.mark_unavailable()
    resumed=detector.observe(20,[PERSON])
    assert resumed.state=='absence'
    assert resumed.present_seconds==0
    assert resumed.alarm is False
    assert detector.observe(21,[]).alarm is True

def test_absence_requires_continuous_thirty_seconds_and_person_resets_timer():
    detector=rule()
    for second in range(30):assert detector.observe(second,[]).transition is None
    first=detector.observe(30,[])
    assert first.transition=='absence' and first.alarm is True
    assert detector.observe(31,[]).transition is None
    assert detector.observe(32,[PERSON]).count==1
    for second in range(33,63):assert detector.observe(second,[]).transition is None
    assert detector.observe(63,[]).transition is None
    assert detector.observe(90,[]).alarm is True

def test_unavailable_frames_and_large_observation_gaps_are_not_absence_evidence():
    detector=rule()
    for second in range(20):detector.observe(second,[])
    detector.mark_unavailable()
    assert detector.observe(50,[]).transition is None
    for second in range(51,80):assert detector.observe(second,[]).transition is None
    assert detector.observe(80,[]).transition=='absence'
    other=rule()
    other.observe(0,[])
    assert other.observe(40,[]).transition is None

def test_roi_counts_person_once_and_ignores_outside_people():
    from app.modules.local_execution.presence import PresenceRule
    detector=PresenceRule([[(0,0),(.5,0),(.5,1),(0,1)]]*2,min_count=2,duration_seconds=1)
    assert detector.observe(0,[PERSON]).count==1
    outside={**PERSON,'x':.7}
    result=detector.observe(1,[PERSON,outside])
    assert result.count==1 and result.transition=='absence'
    assert detector.observe(2,[PERSON,{**PERSON,'x':.3}]).count==2

def test_confirmed_absence_has_one_transition_and_backwards_time_resets_evidence():
    detector=rule(duration_seconds=1,alarm_interval_seconds=3)
    assert detector.observe(0,[]).transition is None
    initial=detector.observe(1,[])
    assert initial.transition=='absence' and initial.alarm is True
    assert detector.observe(2,[]).transition is None
    assert detector.observe(3,[]).transition is None
    repeated=detector.observe(4,[])
    assert repeated.transition is None and repeated.alarm is True
    recovering=detector.observe(5,[PERSON])
    assert recovering.state=='absence' and recovering.alarm is False
    assert detector.observe(6,[]).alarm is False
    repeated_again=detector.observe(7,[])
    assert repeated_again.transition is None and repeated_again.alarm is True
    backwards=detector.observe(0,[PERSON])
    assert backwards.state=='absence' and backwards.present_seconds==0
    assert backwards.alarm is False

def test_large_gap_preserves_confirmed_absence_and_resets_recovery_evidence():
    detector=rule(duration_seconds=2,alarm_interval_seconds=60)
    detector.observe(0,[])
    detector.observe(2,[])
    detector.observe(3,[PERSON])
    after_gap=detector.observe(10,[PERSON])
    assert after_gap.state=='absence'
    assert after_gap.present_seconds==0
    assert after_gap.transition is None
    assert after_gap.alarm is False

def test_zero_alarm_interval_repeats_for_each_observed_absent_frame():
    detector=rule(duration_seconds=1,alarm_interval_seconds=0)
    assert detector.observe(0,[]).alarm is False
    assert detector.observe(1,[]).alarm is True
    assert detector.observe(2,[]).alarm is True
    assert detector.observe(3,[]).alarm is True
    present=detector.observe(4,[PERSON])
    assert present.alarm is False and present.transition is None

@pytest.mark.parametrize('alarm_interval',[30,0])
def test_backwards_time_keeps_absence_and_restarts_repeat_alarm_clock(alarm_interval):
    detector=rule(duration_seconds=1,alarm_interval_seconds=alarm_interval)
    detector.observe(0,[])
    initial=detector.observe(1,[])
    assert initial.state=='absence' and initial.alarm is True

    resumed=detector.observe(0,[])

    assert resumed.state=='absence'
    assert resumed.transition is None
    assert resumed.alarm is True

@pytest.mark.parametrize('settings',[{'min_count':0},{'duration_seconds':0},{'alarm_interval_seconds':-1}])
def test_invalid_presence_settings_are_rejected(settings):
    with pytest.raises(ValueError):rule(**settings)
