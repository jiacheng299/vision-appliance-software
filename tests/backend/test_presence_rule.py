import pytest

REGIONS=[[(0,0),(1,0),(1,1),(0,1)]]
PERSON={'label':'person','x':.2,'y':.2,'width':.2,'height':.5,'confidence':.9}

def rule(**kwargs):
    from app.modules.local_execution.presence import PresenceRule
    return PresenceRule(REGIONS,**kwargs)

def test_absence_and_recovery_each_require_the_full_duration():
    detector=rule(duration_seconds=3)
    assert detector.observe(0,[]).transition is None
    assert detector.observe(3,[]).transition=='absence'
    assert detector.observe(4,[PERSON]).present_seconds==0
    assert detector.observe(6,[PERSON]).transition is None
    restored=detector.observe(7,[PERSON])
    assert restored.transition=='restored'
    assert restored.state=='normal'

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
    detector=rule(duration_seconds=2)
    detector.observe(0,[])
    detector.observe(2,[])
    detector.observe(3,[PERSON])
    detector.mark_unavailable()
    resumed=detector.observe(20,[PERSON])
    assert resumed.state=='absence'
    assert resumed.present_seconds==0

def test_absence_requires_continuous_thirty_seconds_and_person_resets_timer():
    detector=rule()
    for second in range(30):assert detector.observe(second,[]).transition is None
    assert detector.observe(30,[]).transition=='absence'
    assert detector.observe(31,[]).transition is None
    assert detector.observe(32,[PERSON]).count==1
    for second in range(33,63):assert detector.observe(second,[]).transition is None
    assert detector.observe(63,[]).transition is None

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
    assert detector.observe(1,[]).transition=='absence'
    assert detector.observe(2,[]).transition is None
    assert detector.observe(3,[]).transition is None
    assert detector.observe(4,[]).transition is None
    assert detector.observe(0,[]).transition is None

@pytest.mark.parametrize('settings',[{'min_count':0},{'duration_seconds':0},{'alarm_interval_seconds':-1}])
def test_invalid_presence_settings_are_rejected(settings):
    with pytest.raises(ValueError):rule(**settings)
