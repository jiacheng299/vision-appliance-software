"""Correct business routing: fixed templates OR template-first natural language."""
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.modules.models.models import RequirementPlan
from app.modules.agents.schemas import ChannelConfig
from app.modules.models import planning
from app.modules.models.integrations import DemoModelServices
from app.modules.agents.demo import DemoServices
from test_member_a import post, create_agent, publish

API='/api/v1'


@pytest.fixture
def modes(tmp_path, monkeypatch):
    monkeypatch.setenv('VISION_AGENT_DEMO','true')
    app=create_app(var_root=tmp_path,testing=True)
    with TestClient(app) as c:
        post(c,'/agent-demo/seed')
        yield c,app


def channel(c,text='检测是否有人进入区域'):
    sources=c.get(API+'/sources').json()['items']
    return {'channel_id':'group','name':'测试组','task_mode':'natural_language','requirement_text':text,
        'sources':[{'source_id':s['id'],'regions':[{'id':'r','points':[[0,0],[1,0],[0,1]]}]} for s in sources[:2]]}


def bind_multimodal(c):
    selections=c.get(API+'/llm/deployments').json()['selections']
    version=next(s['row_version'] for s in selections if s['usage']=='multimodal_analysis')
    r=c.put(API+'/llm/selections/multimodal_analysis',json={'deployment_id':'MOCK-multimodal','row_version':version})
    assert r.status_code==200,r.text


def plan(c,ch):
    r=post(c,'/requirements/plan',{'channel':ch})
    assert r.status_code==200,r.text
    return r.json()


def test_fixed_fire_does_not_require_language_or_multimodal_model(modes):
    c,_=modes
    template=next(t for t in c.get(API+'/task-templates').json()['items'] if t['name']=='检测火源')
    ch=channel(c,'');ch.update(task_mode='template',target=template['target'],rule=template['rule'],capability_ref=template['capability_ref'])
    for b in ch['sources']:b['regions']=[]
    assert all(s['deployment_id'] is None for s in c.get(API+'/llm/deployments').json()['selections'])
    a=create_agent(c,{'channels':[ch]})
    revision=publish(c,a)
    assert revision['state']=='published'


def test_template_first_match_never_calls_multimodal(modes,monkeypatch):
    c,app=modes
    def unexpected(*args):raise AssertionError('Fallback called despite a full template match')
    monkeypatch.setattr(app.state.model_services,'analyze_multimodal',unexpected)
    result=plan(c,channel(c))
    assert result['strategy']=='template' and result['verdict']=='executable'
    assert result['channel']['capability_ref']['model_id']=='MOCK-person'
    assert result['channel']['execution_plan']['deployment_id'] is None


def test_template_missing_duration_asks_instead_of_falling_back(modes):
    c,_=modes
    result=plan(c,channel(c,'有人在区域内停留太久报警'))
    assert result['strategy']=='template' and result['verdict']=='clarification_required'
    assert result['channel']['duration_seconds'] is None and result['missing_conditions']


def test_partial_match_keeps_extra_attributes_and_uses_multimodal(modes):
    c,_=modes;bind_multimodal(c)
    text='检测是否有穿红色衣服的人进入区域'
    result=plan(c,channel(c,text))
    assert result['strategy']=='multimodal' and result['verdict']=='executable'
    assert result['channel']['capability_ref'] is None
    recipe=result['channel']['execution_plan']
    assert recipe['instruction']==text and recipe['deployment_id']=='MOCK-multimodal'
    assert recipe['deployment_version']=='1.0'


def test_no_templates_still_allows_multimodal_planning(modes,monkeypatch):
    c,app=modes;bind_multimodal(c)
    provider=app.state.agent_services;original=provider.catalog
    def empty(actor):
        value=original(actor);value.items=[];value.fingerprint='empty-catalog-with-vlm';return value
    monkeypatch.setattr(provider,'catalog',empty)
    result=plan(c,channel(c,'识别桌上杯子是否倾倒'))
    assert result['strategy']=='multimodal' and result['verdict']=='executable'
    assert post(c,'/requirements/evaluate',{'config':{'channels':[result['channel']]}}).json()['verdict']=='executable'


def test_fallback_without_deployment_reports_multimodal_dependency(modes):
    c,_=modes
    r=post(c,'/requirements/plan',{'channel':channel(c,'识别桌上的杯子是否倾倒')})
    assert r.status_code==503 and r.json()['error']['code']=='llm_not_selected'


@pytest.mark.parametrize('change',['text','region','duration','instruction','expiry'])
def test_natural_plan_must_be_regenerated_after_any_change(modes,change):
    c,app=modes;bind_multimodal(c)
    result=plan(c,channel(c,'识别区域内的人是否抽烟'))
    ch=result['channel']
    if change=='text':ch['requirement_text']+='并识别吸烟持续时间'
    elif change=='region':ch['sources'][0]['regions']=[]
    elif change=='duration':ch['duration_seconds']=30
    elif change=='instruction':ch['execution_plan']['instruction']='检测火源'
    else:
        with app.state.sessions() as db:
            db.get(RequirementPlan,result['id']).expires_at='2000-01-01T00:00:00Z';db.commit()
    r=post(c,'/requirements/evaluate',{'config':{'channels':[ch]}})
    assert r.status_code==409 and r.json()['error']['code']=='execution_plan_stale'


def test_multimodal_plan_flows_through_publish_and_two_independent_runs(modes):
    c,app=modes;bind_multimodal(c)
    result=plan(c,channel(c,'识别区域内的人是否抽烟'))
    a=create_agent(c,{'channels':[result['channel']]});revision=publish(c,a)
    body={'revision_id':revision['id'],'channel_ids':['group'],'expected_active_run_ids':[]}
    response=post(c,f"/agents/{a['id']}/run-groups",body,key='same-start')
    assert response.status_code==202,response.text
    assert post(c,f"/agents/{a['id']}/run-groups",body,key='same-start').json()['id']==response.json()['id']
    app.state.agent_services.advance(5)
    runs=c.get(API+f"/agents/{a['id']}/workspace").json()['runs']
    assert len(runs)==2 and all(r['state']=='running' for r in runs)
    events=c.get(API+f"/agents/{a['id']}/events").json()['items']
    assert events and all(e['event_type']=='多模态任务事件（模拟）' and '抽烟' in e['reason'] for e in events)
    for run in runs:
        snapshot=run['config_snapshot']['channels'][0]
        assert snapshot['capability_ref'] is None
        assert snapshot['execution_plan']['instruction']=='识别区域内的人是否抽烟'
        assert snapshot['execution_plan']['deployment_id']=='MOCK-multimodal'


def test_expired_plan_cannot_start_even_with_fresh_revision_validation(modes):
    c,app=modes;bind_multimodal(c)
    result=plan(c,channel(c,'识别是否有人抽烟'))
    a=create_agent(c,{'channels':[result['channel']]});revision=publish(c,a)
    with app.state.sessions() as db:
        db.get(RequirementPlan,result['id']).expires_at='2000-01-01T00:00:00Z';db.commit()
    r=post(c,f"/agents/{a['id']}/run-groups",{'revision_id':revision['id'],'channel_ids':['group'],'expected_active_run_ids':[]})
    assert r.status_code==409


def test_forged_or_missing_natural_plan_is_not_executable(modes):
    c,_=modes
    ch=channel(c)
    ref=c.get(API+'/capabilities/models').json()['items'][0]['reference']
    ch.update(target='person',rule='intrusion',capability_ref=ref)
    assert post(c,'/requirements/evaluate',{'config':{'channels':[ch]}}).status_code==409


def test_template_does_not_accept_hidden_extra_natural_requirements(modes):
    c,_=modes
    t=next(t for t in c.get(API+'/task-templates').json()['items'] if t['name']=='检测是否有人进入区域')
    ch=channel(c,'检测红衣服的人进入区域');ch.update(task_mode='template',target=t['target'],rule=t['rule'],capability_ref=t['capability_ref'])
    assert post(c,'/requirements/evaluate',{'config':{'channels':[ch]}}).json()['verdict']=='unsupported'


def test_legacy_serialization_omits_new_fields():
    value=ChannelConfig(name='old',requirement_text='old')
    assert 'task_mode' not in value.model_dump() and 'execution_plan' not in value.model_dump()


def test_conflicting_duration_is_exposed_instead_of_silently_overridden(modes):
    c,_=modes
    ch=channel(c,'有人在区域内停留超过30秒报警');ch['duration_seconds']=60
    result=plan(c,ch)
    assert result['verdict']=='clarification_required' and any('不一致' in m for m in result['missing_conditions'])
    assert result['channel']['duration_seconds']==60
