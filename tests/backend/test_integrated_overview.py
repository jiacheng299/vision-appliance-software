"""The overview must report the same Run/Event owner used by agent workspaces."""
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from test_member_a import post, publish

API='/api/v1'


def test_unconnected_runtime_is_unknown_instead_of_zero(client):
    dashboard=client.get(API+'/dashboard').json()
    assert dashboard['counts']['active_runs'] is None
    assert dashboard['counts']['today_events'] is None
    assert dashboard['task_summary']['running'] is None
    assert dashboard['runtime_available'] is False and dashboard['events_available'] is False
    runtime=client.get(API+'/runtime/overview').json()
    assert runtime['runs']['running'] is None and runtime['runtime_available'] is False
    assert client.get(API+'/events').json()['available'] is False


@pytest.fixture
def running_demo(tmp_path,monkeypatch):
    monkeypatch.setenv('VISION_AGENT_DEMO','true')
    app=create_app(var_root=tmp_path,testing=True)
    with TestClient(app) as client:
        agent=post(client,'/agent-demo/seed').json()
        revision=publish(client,agent)
        response=post(client,'/agents/'+agent['id']+'/run-groups',{'revision_id':revision['id'],'channel_ids':[c['channel_id'] for c in revision['config']['channels']],'expected_active_run_ids':[]})
        assert response.status_code==202,response.text
        app.state.agent_services.advance(8)
        yield client,app,agent


def test_overview_and_event_list_use_agent_run_and_event_snapshots(running_demo):
    client,app,agent=running_demo
    workspace=client.get(API+'/agents/'+agent['id']+'/workspace').json()
    dashboard=client.get(API+'/dashboard').json()
    assert dashboard['data_origin']=='mock' and dashboard['runtime_available'] is True
    assert dashboard['counts']['active_runs']==len(workspace['runs'])==2
    assert dashboard['task_summary']['running']==2
    events=client.get(API+'/agents/'+agent['id']+'/events').json()
    assert dashboard['counts']['today_events']==events['today_count']==2
    assert {e['id'] for e in dashboard['recent_events']}=={e['id'] for e in events['items']}
    assert all(e['agent_id']==agent['id'] and e['source_name'] for e in dashboard['recent_events'])
    assert client.get(API+'/events').json()['items']==dashboard['recent_events']
    assert client.get(API+'/runtime/overview').json()['runs']['running']==2


def test_event_failure_does_not_hide_healthy_runtime_totals(running_demo):
    client,app,_=running_demo
    app.state.agent_services.set_scenario('events_disconnected')
    result=client.get(API+'/dashboard').json()
    assert result['runtime_available'] is True and result['counts']['active_runs']==2
    assert result['events_available'] is False and result['counts']['today_events'] is None
    assert result['recent_events']==[]


def test_today_count_uses_same_timezone_as_agent_events(running_demo):
    client,app,_=running_demo
    provider=app.state.agent_services
    event=next(iter(provider.event_rows.values())).model_copy(deep=True)
    event.id='previous-day-event'
    event.occurred_at=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat().replace('+00:00','Z')
    provider.event_rows[event.id]=event
    result=client.get(API+'/dashboard').json()
    assert result['counts']['today_events']==2
    assert len(result['recent_events'])==3


def test_connected_empty_demo_reports_verified_zero(tmp_path,monkeypatch):
    monkeypatch.setenv('VISION_AGENT_DEMO','true')
    with TestClient(create_app(var_root=tmp_path,testing=True)) as client:
        result=client.get(API+'/dashboard').json()
        assert result['runtime_available'] is True and result['events_available'] is True
        assert result['counts']['active_runs']==0 and result['counts']['today_events']==0
