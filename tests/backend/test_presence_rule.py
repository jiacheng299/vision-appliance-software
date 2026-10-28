import pytest

REGIONS=[[(0,0),(1,0),(1,1),(0,1)]]
PERSON={'label':'person','x':.2,'y':.2,'width':.2,'height':.5,'confidence':.9}

def rule(**kwargs):
    from app.modules.local_execution.presence import PresenceRule
    return PresenceRule(REGIONS,**kwargs)

def test_absence_requires_continuous_thirty_seconds_and_person_resets_timer():
    detector=rule()
    for second in range(30):assert not detector.observe(second,[]).alarm
    assert detector.observe(30,[]).alarm
    assert not detector.observe(31,[]).alarm
    assert detector.observe(32,[PERSON]).count==1
    for second in range(33,63):assert not detector.observe(second,[]).alarm
    assert detector.observe(63,[]).alarm

def test_unavailable_frames_and_large_observation_gaps_are_not_absence_evidence():
    detector=rule()
    for second in range(20):detector.observe(second,[])
    detector.mark_unavailable()
    assert not detector.observe(50,[]).alarm
    for second in range(51,80):assert not detector.observe(second,[]).alarm
    assert detector.observe(80,[]).alarm
    other=rule()
    other.observe(0,[])
    assert not other.observe(40,[]).alarm

def test_roi_counts_person_once_and_ignores_outside_people():
    from app.modules.local_execution.presence import PresenceRule
    detector=PresenceRule([[(0,0),(.5,0),(.5,1),(0,1)]]*2,min_count=2,duration_seconds=1)
    assert detector.observe(0,[PERSON]).count==1
    outside={**PERSON,'x':.7}
    result=detector.observe(1,[PERSON,outside])
    assert result.count==1 and result.alarm
    assert detector.observe(2,[PERSON,{**PERSON,'x':.3}]).count==2

def test_repeated_alarms_obey_interval_and_backwards_time_resets_evidence():
    detector=rule(duration_seconds=1,alarm_interval_seconds=3)
    assert not detector.observe(0,[]).alarm
    assert detector.observe(1,[]).alarm
    assert not detector.observe(2,[]).alarm
    assert not detector.observe(3,[]).alarm
    assert detector.observe(4,[]).alarm
    assert not detector.observe(0,[]).alarm

@pytest.mark.parametrize('settings',[{'min_count':0},{'duration_seconds':0},{'alarm_interval_seconds':-1}])
def test_invalid_presence_settings_are_rejected(settings):
    with pytest.raises(ValueError):rule(**settings)
