"""B workflow acceptance using explicit public-service test doubles, never real inference."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import json
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.modules.agents.demo import DemoServices
from app.modules.agents.models import AgentRevision, AgentValidation
from app.shared.models import Source

API='/api/v1'


@pytest.fixture
def demo(tmp_path):
    provider=DemoServices()
    app=create_app(var_root=tmp_path,testing=True,agent_services=provider)
    # Deferred implementation retains contract coverage; the release defaults off.
    app.state.config.manual_review_enabled=True
    with TestClient(app) as client:
        response=client.post(API+'/agent-demo/seed')
        assert response.status_code==200,response.text
        yield client,provider,response.json(),app


def post(client,path,body=None,key=None):
    return client.post(API+path,json=body,headers={'Idempotency-Key':key or str(uuid4())})


def test_manual_review_release_gate_preserves_read_only_events(tmp_path):
    provider=DemoServices()
    app=create_app(var_root=tmp_path,testing=True,agent_services=provider)
    assert app.state.config.manual_review_enabled is False
    with TestClient(app) as c:
        a=c.post(API+'/agent-demo/seed').json()
        _,runs=start_demo(c,provider,a)
        event=c.get(API+f"/agents/{a['id']}/events").json()['items'][0]
        response=post(c,f"/agents/{a['id']}/events/{event['id']}/feedback",{'label':'correct','reason':'test','row_version':event['row_version']})
        assert response.status_code==503 and response.json()['error']['code']=='feature_not_available'
        response=post(c,f"/agents/{a['id']}/missed-annotations",{'run_id':runs[0]['id'],'event_type':'test','description':'test'})
        assert response.status_code==503
        assert c.get(API+f"/agents/{a['id']}/events/{event['id']}").json()['feedback_history']==[]


def detail(client,agent):
    response=client.get(API+'/agents/'+agent['id']);assert response.status_code==200,response.text
    return response.json()


def revision(client,rid):
    return client.get(API+'/revisions/'+rid).json()


def publish(client,agent,rid=None):
    rev=revision(client,rid) if rid else detail(client,agent)['latest_revision']
    result=post(client,f"/revisions/{rev['id']}/validations",{'row_version':rev['row_version']})
    assert result.status_code==201,result.text
    value=result.json();assert value['verdict']=='executable',value
    rev=revision(client,rev['id'])
    result=post(client,f"/revisions/{rev['id']}/confirmations",{'row_version':rev['row_version'],'validation_id':value['id'],'config_hash':value['config_hash'],'limitations_acknowledged':True})
    assert result.status_code==200,result.text
    return result.json(),value


def submit(client,agent,rev,kind='start',run_ids=None,channel_ids=None,key=None):
    path='run-groups' if kind=='start' else 'revision-applications'
    return post(client,f"/agents/{agent['id']}/{path}",{'revision_id':rev['id'],'channel_ids':channel_ids or [c['channel_id'] for c in rev['config']['channels']],'expected_active_run_ids':run_ids or []},key)


def finish(client,provider,agent,op):
    provider.advance(3)
    result=client.get(API+f"/agents/{agent['id']}/operations/{op['id']}")
    assert result.status_code==200,result.text
    return result.json()


def workspace(client,agent):
    result=client.get(API+f"/agents/{agent['id']}/workspace");assert result.status_code==200,result.text
    return result.json()['runs']


def start_demo(client,provider,agent):
    rev,_=publish(client,agent)
    result=submit(client,agent,rev);assert result.status_code==202,result.text
    assert result.json()['state']=='pending'
    assert finish(client,provider,agent,result.json())['state']=='succeeded'
    return rev,workspace(client,agent)


def test_detection_frame_route_keeps_run_scope_and_disables_caching(demo):
    client,provider,agent,_=demo
    _,runs=start_demo(client,provider,agent)
    run=runs[0]
    provider.detection_frame=lambda run,actor: (b'jpeg-pixels','2026-10-30T00:00:00Z')
    path=f"/agents/{agent['id']}/runs/{run['id']}/detection-frame"
    response=client.get(API+path)
    assert response.status_code==200 and response.content==b'jpeg-pixels'
    assert response.headers['content-type']=='image/jpeg'
    assert response.headers['cache-control']=='no-store'
    assert response.headers['x-detection-observed-at']=='2026-10-30T00:00:00Z'
    provider.detection_frame=lambda run,actor: None
    assert client.get(API+path).status_code==204
    assert client.get(API+path.replace(run['id'],'not-a-run')).status_code==404
    assert client.get(API+path.replace(agent['id'],'not-an-agent')).status_code==404


def test_detection_stream_is_scoped_and_delivers_complete_jpegs(demo):
    client,provider,agent,_=demo
    _,runs=start_demo(client,provider,agent)
    run=runs[0]
    frames=iter([(b'one','time-1'),(b'two','time-2'),None])
    provider.detection_frame=lambda run,actor: next(frames)
    path=f"/agents/{agent['id']}/runs/{run['id']}/detection-stream"
    response=client.get(API+path)
    assert response.status_code==200
    assert response.headers['content-type']=='multipart/x-mixed-replace; boundary=vision-frame'
    assert response.headers['cache-control']=='no-store'
    assert response.content.count(b'--vision-frame')==2
    assert b'\r\n\r\none\r\n' in response.content and b'\r\n\r\ntwo\r\n' in response.content
    assert client.get(API+path.replace(run['id'],'not-a-run')).status_code==404


def clone(client,agent,base):
    result=post(client,f"/agents/{agent['id']}/revisions",{'base_revision_id':base['id'],'row_version':detail(client,agent)['row_version']})
    assert result.status_code==201,result.text
    return result.json()


def stop_all(client,provider,agent,runs):
    for run in runs:
        result=post(client,f"/agents/{agent['id']}/runs/{run['id']}/stop")
        assert result.status_code==202,result.text
        assert finish(client,provider,agent,result.json())['state']=='succeeded'


def test_default_mode_never_exposes_demo_or_fake_runs(client):
    assert client.get(API+'/agent-environment').json()['data_origin']=='real'
    assert client.post(API+'/agent-demo/seed').status_code==404
    assert client.post(API+'/agent-demo/scenario',json={'scenario':'normal'}).status_code==404
    agent=post(client,'/agents',{'name':'real draft'}).json()
    w=client.get(API+f"/agents/{agent['id']}/workspace").json()
    assert w['runtime_available'] is False and w['runs']==[]


def test_delete_task_removes_definitions_runs_and_events_but_keeps_sources(demo):
    c,p,a,app=demo
    rev,runs=start_demo(c,p,a)
    source_ids=[r['source_id'] for r in runs]
    clone(c,a,rev)
    current=detail(c,a)
    bad=c.delete(API+f"/agents/{a['id']}",params={'row_version':current['row_version']+1})
    assert bad.status_code==409,bad.text
    assert len(workspace(c,a))==2
    result=c.delete(API+f"/agents/{a['id']}",params={'row_version':current['row_version']})
    assert result.status_code==204,result.text
    assert c.get(API+f"/agents/{a['id']}").status_code==404
    assert c.get(API+f"/revisions/{rev['id']}").status_code==404
    assert p.runs(a['id'],'workspace')==[]
    assert not any(r.agent_id==a['id'] for r in p.run_rows.values())
    assert not any(e.agent_id==a['id'] for e in p.event_rows.values())
    with app.state.sessions() as db:
        assert all(db.get(Source,sid) is not None for sid in source_ids)
        assert not db.query(AgentValidation).filter(AgentValidation.revision_id==rev['id']).count()


def test_delete_unpublished_task_without_runtime(client):
    task=post(client,'/agents',{'name':'disposable draft'}).json()
    result=client.delete(API+f"/agents/{task['id']}",params={'row_version':task['row_version']})
    assert result.status_code==204,result.text
    assert client.get(API+f"/agents/{task['id']}").status_code==404


def test_demo_database_isolation_and_repeat_prepare(tmp_path,monkeypatch):
    from app.shared.config import Config
    config=Config(var_root=tmp_path,agent_demo=True);config.prepare();first=config.var_root;config.prepare()
    assert config.var_root==first==tmp_path/'agent-demo'
    monkeypatch.setenv('VISION_AGENT_DEMO','true')
    app=create_app(var_root=tmp_path,testing=True)
    assert app.state.config.var_root==tmp_path/'agent-demo'
    assert not (tmp_path/'vision.db').exists()
    app.state.engine.dispose()
    monkeypatch.delenv('VISION_AGENT_DEMO')
    with pytest.raises(RuntimeError):
        create_app(var_root=tmp_path,agent_services=DemoServices())


def test_validate_confirm_freezes_snapshot_and_does_not_start(demo):
    c,p,a,app=demo
    rev,value=publish(c,a)
    assert value['data_origin']=='mock' and rev['state']=='published'
    assert workspace(c,a)==[]
    assert detail(c,a)['desired_revision_id']==rev['id']
    result=c.patch(API+'/revisions/'+rev['id'],json={'row_version':rev['row_version'],'config':rev['config']})
    assert result.status_code==409
    assert detail(c,a)['status']=='ready'


def test_missing_conditions_and_unsupported_are_never_ignored(demo):
    c,p,a,_=demo
    rev=a['latest_revision'];config=rev['config'];config['channels'][0]['regions']=[]
    edited=c.patch(API+'/revisions/'+rev['id'],json={'row_version':rev['row_version'],'config':config}).json()
    value=post(c,f"/revisions/{rev['id']}/validations",{'row_version':edited['row_version']}).json()
    assert value['verdict']=='clarification_required' and value['missing_conditions']
    rev=revision(c,rev['id'])
    assert post(c,f"/revisions/{rev['id']}/confirmations",{'row_version':rev['row_version'],'validation_id':value['id'],'config_hash':value['config_hash'],'limitations_acknowledged':True}).status_code==422
    config['channels'][0]['target']='unsupported_target'
    edited=c.patch(API+'/revisions/'+rev['id'],json={'row_version':rev['row_version'],'config':config}).json()
    value=post(c,f"/revisions/{rev['id']}/validations",{'row_version':edited['row_version']}).json()
    assert value['unsupported_conditions']
    assert workspace(c,a)==[]


@pytest.mark.parametrize('change',['expiry','model','source'])
def test_confirmation_rejects_expired_or_changed_dependencies(demo,change):
    c,p,a,app=demo;rev=a['latest_revision']
    value=post(c,f"/revisions/{rev['id']}/validations",{'row_version':rev['row_version']}).json();rev=revision(c,rev['id'])
    if change=='model':p.fingerprint='changed'
    else:
        with app.state.sessions() as db:
            if change=='expiry':db.get(AgentValidation,value['id']).expires_at='2000-01-01T00:00:00Z'
            else:db.get(Source,rev['config']['channels'][0]['source_id']).row_version+=1
            db.commit()
    result=post(c,f"/revisions/{rev['id']}/confirmations",{'row_version':rev['row_version'],'validation_id':value['id'],'config_hash':value['config_hash'],'limitations_acknowledged':True})
    assert result.status_code==409,result.text
    assert revision(c,rev['id'])['state']=='draft'


def test_edit_during_external_assessment_rejects_stale_result(demo):
    c,p,a,app=demo;rid=a['latest_revision']['id'];original=p.assess
    def assess(config,sources,actor):
        result=original(config,sources,actor)
        with app.state.sessions() as db:
            rev=db.get(AgentRevision,rid);rev.row_version+=1;db.commit()
        return result
    p.assess=assess
    result=post(c,f'/revisions/{rid}/validations',{'row_version':1})
    assert result.status_code==409,result.text
    assert revision(c,rid)['latest_validation_id'] is None


def test_start_has_async_result_and_retries_are_idempotent(demo):
    c,p,a,_=demo;rev,_=publish(c,a);key=str(uuid4())
    result=submit(c,a,rev,key=key);assert result.status_code==202,result.text
    assert result.json()['state']=='pending' and workspace(c,a)==[]
    assert finish(c,p,a,result.json())['state']=='succeeded'
    first=workspace(c,a);assert len(first)==2 and all(r['state']=='running' for r in first)
    p.scenario='model_unavailable'
    repeated=submit(c,a,rev,key=key)
    assert repeated.status_code==202 and repeated.json()['id']==result.json()['id']
    assert len(workspace(c,a))==2


def test_published_task_can_restart_after_validation_expiry(demo):
    c,p,a,app=demo
    rev,value=publish(c,a)
    p.scenario='start_failed'
    first=submit(c,a,rev)
    assert first.status_code==202,first.text
    finish(c,p,a,first.json())
    stop_all(c,p,a,[r for r in workspace(c,a) if r['state']=='running'])
    with app.state.sessions() as db:
        db.get(AgentValidation,value['id']).expires_at='2000-01-01T00:00:00Z'
        db.commit()
    p.scenario='normal'
    restarted=submit(c,a,rev)
    assert restarted.status_code==202,restarted.text
    assert finish(c,p,a,restarted.json())['state']=='succeeded'
    assert any(r['state']=='running' for r in workspace(c,a))


@pytest.mark.parametrize('change',['model'])
def test_published_restart_rejects_changed_dependencies(demo,change):
    c,p,a,app=demo
    rev,_=publish(c,a)
    if change=='model':
        p.fingerprint='changed'
    else:
        with app.state.sessions() as db:
            db.get(Source,rev['config']['channels'][0]['source_id']).row_version+=1
            db.commit()
    result=submit(c,a,rev)
    assert result.status_code==409,result.text
    assert result.json()['error']['code']=='validation_stale'


def test_published_restart_reassesses_updated_source_without_cloning(demo):
    c,p,a,app=demo
    rev,_=publish(c,a)
    before=detail(c,a)['revisions']
    with app.state.sessions() as db:
        db.get(Source,rev['config']['channels'][0]['source_id']).row_version+=1
        db.commit()
    result=submit(c,a,rev)
    assert result.status_code==202,result.text
    assert finish(c,p,a,result.json())['state']=='succeeded'
    assert detail(c,a)['revisions']==before


def test_restart_with_updated_source_still_rejects_failed_assessment(demo):
    c,p,a,app=demo
    rev,_=publish(c,a)
    with app.state.sessions() as db:
        db.get(Source,rev['config']['channels'][0]['source_id']).row_version+=1
        db.commit()
    p.scenario='insufficient_evidence'
    result=submit(c,a,rev)
    assert result.status_code==422,result.text
    assert result.json()['error']['code']=='validation_blocked'
    assert workspace(c,a)==[]


def test_edit_while_running_only_changes_draft_and_old_events_keep_version(demo):
    c,p,a,_=demo;old,runs=start_demo(c,p,a)
    draft=clone(c,a,old);config=draft['config'];config['channels'][0]['duration_seconds']=60
    assert c.patch(API+'/revisions/'+draft['id'],json={'row_version':1,'config':config}).status_code==200
    assert all(r['revision_id']==old['id'] and r['state']=='running' for r in workspace(c,a))
    assert revision(c,old['id'])['config']['channels'][0]['duration_seconds']==30
    page=c.get(API+f"/agents/{a['id']}/events").json()
    assert page['items'] and all(e['revision_id']==old['id'] for e in page['items'])


def test_apply_stops_old_and_creates_new_runs(demo):
    c,p,a,_=demo;old,runs=start_demo(c,p,a);draft=clone(c,a,old);new,_=publish(c,a,draft['id'])
    result=submit(c,a,new,'apply',[r['id'] for r in runs]);assert result.status_code==202,result.text
    assert finish(c,p,a,result.json())['state']=='succeeded'
    all_runs=workspace(c,a)
    assert all(r['state']=='stopped' for r in all_runs if r['revision_id']==old['id'])
    assert len([r for r in all_runs if r['revision_id']==new['id'] and r['state']=='running'])==2
    assert not set(r['id'] for r in runs)&set(r['id'] for r in all_runs if r['revision_id']==new['id'])


def test_failed_restart_preserves_history_and_can_restart_old_version(demo):
    c,p,a,_=demo;old,runs=start_demo(c,p,a);draft=clone(c,a,old);new,_=publish(c,a,draft['id']);p.scenario='start_failed'
    result=submit(c,a,new,'apply',[r['id'] for r in runs]);operation=finish(c,p,a,result.json())
    assert operation['state']=='partial_failed'
    failed=next(x for x in operation['channels'] if x['state']=='failed')
    all_runs=workspace(c,a)
    assert next(r for r in all_runs if r['id']==failed['old_run_id'])['state']=='stopped'
    assert next(r for r in all_runs if r['id']==failed['new_run_id'])['state']=='failed'
    p.scenario='normal'
    result=submit(c,a,old,channel_ids=[failed['channel_id']]);assert result.status_code==202,result.text
    assert finish(c,p,a,result.json())['state']=='succeeded'
    active=[r for r in workspace(c,a) if r['state']=='running']
    assert {r['revision_id'] for r in active}=={old['id'],new['id']}
    assert failed['old_run_id'] not in {r['id'] for r in active}


def test_stop_failure_does_not_claim_new_version_applied(demo):
    c,p,a,_=demo;old,runs=start_demo(c,p,a);new,_=publish(c,a,clone(c,a,old)['id']);p.scenario='stop_failed'
    operation=finish(c,p,a,submit(c,a,new,'apply',[r['id'] for r in runs]).json())
    failed=next(x for x in operation['channels'] if x['state']=='failed')
    assert failed['new_run_id'] is None
    assert next(r for r in workspace(c,a) if r['id']==failed['old_run_id'])['state']=='running'


def test_scope_conflict_and_one_failed_channel_do_not_stop_others(demo):
    c,p,a,_=demo;rev,runs=start_demo(c,p,a)
    conflict=submit(c,a,rev,'apply',run_ids=['wrong-id'])
    assert conflict.status_code==409
    p.set_scenario('run_failed',runs[0]['id'])
    result=workspace(c,a)
    assert next(r for r in result if r['id']==runs[1]['id'])['state']=='running'
    assert next(r for r in result if r['id']==runs[0]['id'])['state']=='failed'


def test_queue_is_not_running_and_stop_works_without_model_service(demo):
    c,p,a,_=demo;rev,_=publish(c,a);p.scenario='resource_queued'
    result=submit(c,a,rev);finish(c,p,a,result.json());runs=workspace(c,a)
    assert all(r['state']=='queued' and r['started_at'] is None for r in runs)
    assert detail(c,a)['status']=='queued'
    p.scenario='model_unavailable'
    result=post(c,f"/agents/{a['id']}/runs/{runs[0]['id']}/stop")
    assert result.status_code==202,result.text
    assert finish(c,p,a,result.json())['state']=='succeeded'


def test_feedback_is_append_only_correlated_and_sse_updates(demo):
    c,p,a,_=demo;rev,runs=start_demo(c,p,a)
    page=c.get(API+f"/agents/{a['id']}/events").json();event=page['items'][0];key=str(uuid4());body={'label':'false_positive','reason':'模拟核查：目标识别错误','row_version':event['row_version']}
    result=post(c,f"/agents/{a['id']}/events/{event['id']}/feedback",body,key)
    assert result.status_code==200,result.text
    updated=result.json();assert updated['review_status']=='false_positive' and len(updated['feedback_history'])==1
    assert updated['revision_id']==rev['id'] and updated['run_id']==event['run_id']
    assert post(c,f"/agents/{a['id']}/events/{event['id']}/feedback",body,key).json()==updated
    assert post(c,f"/agents/{a['id']}/events/{event['id']}/feedback",body).status_code==409
    second=post(c,f"/agents/{a['id']}/events/{event['id']}/feedback",{**body,'label':'correct','row_version':updated['row_version']}).json()
    assert len(second['feedback_history'])==2 and second['feedback_history'][0]['label']=='false_positive'
    stream=c.get(API+f"/agents/{a['id']}/event-stream",params={'after':page['stream_cursor'],'once':True})
    assert stream.status_code==200 and 'event: events' in stream.text and event['id'] in stream.text
    assert post(c,f"/agents/{a['id']}/events/{event['id']}/feedback",{**body,'revision_id':'forged'}).status_code==422


def test_service_outages_leave_history_and_configuration_readable(demo):
    c,p,a,_=demo;rev,runs=start_demo(c,p,a)
    p.scenario='video_disconnected'
    assert post(c,f"/agents/{a['id']}/runs/{runs[0]['id']}/playback").status_code==503
    assert c.get(API+f"/agents/{a['id']}/events").status_code==200
    p.scenario='events_disconnected'
    assert detail(c,a)['latest_revision']['id']==rev['id']
    assert c.get(API+f"/agents/{a['id']}/event-stream").status_code==503
    p.scenario='model_unavailable'
    assert detail(c,a)['revisions'] and c.get(API+f"/agents/{a['id']}/events").status_code==200


def test_missing_evidence_is_not_fabricated_and_sessions_are_scoped(demo):
    c,p,a,_=demo;rev,runs=start_demo(c,p,a)
    event=c.get(API+f"/agents/{a['id']}/events").json()['items'][0]
    row=p.event_rows[event['id']];row.evidence_status='missing';row.evidence[0].state='missing'
    value=c.get(API+f"/agents/{a['id']}/events/{event['id']}").json()
    result=post(c,f"/agents/{a['id']}/events/{event['id']}/evidence/{value['evidence'][0]['id']}/access-sessions")
    assert result.status_code==409
    playback=post(c,f"/agents/{a['id']}/runs/{runs[0]['id']}/playback").json()
    assert playback['data_origin']=='mock' and playback['protocol']=='mock' and playback['playback_url'] is None
    assert c.delete(API+f"/agents/{a['id']}/playback-sessions/{playback['id']}").status_code==200
    assert playback['id'] not in p.sessions


def test_missed_file_range_and_live_time_are_server_checked(demo):
    c,p,a,app=demo
    rev,runs=start_demo(c,p,a);file=next(r for r in runs if r['source_kind']=='file');live=next(r for r in runs if r['source_kind']=='camera')
    base={'run_id':file['id'],'event_type':'人员滞留','description':'模拟人工标注','start_media_ms':0,'end_media_ms':1000}
    result=post(c,f"/agents/{a['id']}/missed-annotations",base)
    assert result.status_code==201,result.text
    assert result.json()['revision_id']==rev['id'] and result.json()['source_id']==file['source_id']
    assert post(c,f"/agents/{a['id']}/missed-annotations",{**base,'end_media_ms':60001}).status_code==422
    assert post(c,f"/agents/{a['id']}/missed-annotations",{**base,'revision_id':'forged'}).status_code==422
    live_body={'run_id':live['id'],'event_type':'行为','description':'无回放证据的模拟记录'}
    assert post(c,f"/agents/{a['id']}/missed-annotations",live_body).status_code==422
    assert post(c,f"/agents/{a['id']}/missed-annotations",{**live_body,'start_media_ms':0,'end_media_ms':1000}).status_code==422
    live_body['occurred_at']=datetime.now(timezone.utc).isoformat()
    assert post(c,f"/agents/{a['id']}/missed-annotations",live_body).status_code==201
    page=c.get(API+f"/agents/{a['id']}/events").json()
    assert len(page['items'])==2 # manual annotations never become system detections


def test_retest_keeps_selected_channel_baseline_and_creates_new_run(demo):
    c,p,a,_=demo;rev,runs=start_demo(c,p,a);stop_all(c,p,a,runs)
    result=post(c,f"/agents/{a['id']}/retests",{'baseline_run_id':runs[0]['id'],'row_version':detail(c,a)['row_version']})
    assert result.status_code==201,result.text
    draft=result.json();assert draft['baseline_run_id']==runs[0]['id'] and len(draft['config']['channels'])==1
    published,_=publish(c,a,draft['id']);op=submit(c,a,published);assert op.status_code==202,op.text
    finish(c,p,a,op.json());candidate=next(r for r in workspace(c,a) if r['revision_id']==published['id'])
    comparison=c.get(API+f"/agents/{a['id']}/comparisons",params={'baseline_run_id':runs[0]['id'],'candidate_run_id':candidate['id']})
    assert comparison.status_code==200 and comparison.json()['comparable'] is False
    assert 'accuracy' not in comparison.json()['candidate']


def test_export_failure_retry_keeps_original_snapshot_and_mock_marking(demo):
    c,p,a,_=demo;rev,runs=start_demo(c,p,a);p.scenario='export_failed'
    result=post(c,f"/agents/{a['id']}/exports",{'run_ids':[runs[0]['id']],'contents':['report','images'],'destination':'browser'})
    assert result.status_code==202,result.text
    job=result.json();p.advance(2)
    assert c.get(API+f"/agents/{a['id']}/exports/{job['id']}").json()['state']=='failed'
    original=json.dumps(p.job_payloads[job['id']],sort_keys=True)
    p.scenario='normal';retried=post(c,f"/agents/{a['id']}/exports/{job['id']}/retry").json();p.advance(6)
    complete=c.get(API+f"/agents/{a['id']}/exports/{retried['id']}").json()
    assert complete['state']=='succeeded' and json.dumps(p.job_payloads[retried['id']],sort_keys=True)==original
    download=c.get(complete['download_url']);assert download.status_code==200
    assert download.json()['WARNING']=='MOCK_NOT_A_VALIDATION_REPORT'
    assert 'MOCK_NOT_A_REPORT.json' in download.headers['content-disposition']


def test_archive_is_recoverable_but_refuses_active_runs(demo):
    c,p,a,_=demo;rev,runs=start_demo(c,p,a)
    result=post(c,f"/agents/{a['id']}/archive",{'row_version':detail(c,a)['row_version']})
    assert result.status_code==409
    stop_all(c,p,a,runs)
    assert post(c,f"/agents/{a['id']}/archive",{'row_version':detail(c,a)['row_version']}).status_code==200
    assert c.get(API+'/agents').json()['items']==[]
    assert len(c.get(API+'/agents',params={'archived':True}).json()['items'])==1
    current=detail(c,a);assert current['status']=='archived'
    assert submit(c,a,rev).status_code==409
    assert post(c,f"/agents/{a['id']}/restore",{'row_version':current['row_version']}).status_code==200
    assert len(c.get(API+'/agents').json()['items'])==1


def test_pending_start_prevents_archive_and_reference_api_is_authoritative(demo):
    c,p,a,_=demo;rev,_=publish(c,a)
    operation=submit(c,a,rev).json()
    assert post(c,f"/agents/{a['id']}/archive",{'row_version':detail(c,a)['row_version']}).status_code==409
    finish(c,p,a,operation)
    result=c.get(API+'/agent-services/references',params={'model_id':'MOCK-person','model_version':'1.0'}).json()
    assert result['items'] and result['items'][0]['runtime_checked'] is True
    assert len(result['items'][0]['active_run_ids'])==2
    assert result['items'][0]['revision_id']==rev['id']


def test_host_export_only_accepts_approved_aliases(demo):
    c,p,a,_=demo;_,runs=start_demo(c,p,a)
    base={'run_ids':[runs[0]['id']],'contents':['report'],'destination':'host'}
    assert post(c,f"/agents/{a['id']}/exports",{**base,'destination_alias':'C:/private'}).status_code==422
    assert post(c,f"/agents/{a['id']}/exports",base).status_code==422
    result=post(c,f"/agents/{a['id']}/exports",{**base,'destination_alias':'mock-host'})
    assert result.status_code==202,result.text
    p.advance(6)
    job=c.get(API+f"/agents/{a['id']}/exports/{result.json()['id']}").json()
    assert job['state']=='succeeded' and job['download_url'] is None
    assert '没有向实际目录写入' in job['message']


def test_other_agent_cannot_control_runs_or_feedback(demo):
    c,p,a,_=demo;rev,runs=start_demo(c,p,a);event=c.get(API+f"/agents/{a['id']}/events").json()['items'][0]
    other=post(c,'/agents',{'name':'其他智能体'}).json()
    assert post(c,f"/agents/{other['id']}/runs/{runs[0]['id']}/stop").status_code==404
    assert c.get(API+f"/agents/{other['id']}/events/{event['id']}").status_code==404
    assert post(c,f"/agents/{other['id']}/exports",{'run_ids':[runs[0]['id']],'contents':['report']}).status_code==404


def test_event_pagination_and_incremental_replay_do_not_skip_a_backlog(demo):
    c,p,a,_=demo;_,runs=start_demo(c,p,a)
    for _ in range(5):p.add_event(p.run_rows[runs[0]['id']])
    first=c.get(API+f"/agents/{a['id']}/events",params={'limit':2}).json()
    seen={e['id'] for e in first['items']};cursor=first['next_cursor']
    while cursor:
        page=c.get(API+f"/agents/{a['id']}/events",params={'limit':2,'cursor':cursor}).json()
        assert not seen & {e['id'] for e in page['items']}
        seen.update(e['id'] for e in page['items']);cursor=page['next_cursor']
    assert len(seen)==7
    cursor='0';replayed=set()
    while int(cursor)<p.sequence:
        page=p.events(a['id'],'test',{'limit':2},after=cursor)
        assert int(page.stream_cursor)>int(cursor)
        replayed.update(e.id for e in page.items);cursor=page.stream_cursor
    assert replayed==seen


def grouped(demo):
    c,p,a,app=demo
    rev=detail(c,a)['latest_revision'];left,right=rev['config']['channels']
    def binding(channel):return {k:channel[k] for k in ('source_id','regions','start_media_ms','end_media_ms')}
    left['sources']=[binding(left),binding(right)]
    left.update(source_id=None,regions=[],start_media_ms=None,end_media_ms=None)
    rev['config']['channels']=[left]
    result=c.patch(API+f"/revisions/{rev['id']}",json={'config':rev['config'],'row_version':rev['row_version']})
    assert result.status_code==200,result.text
    return c,p,a,app,result.json()


def test_group_sources_have_independent_runs_events_regions_and_group_stop(demo):
    c,p,a,_,rev=grouped(demo);rev,_=publish(c,a)
    op=submit(c,a,rev).json();assert len(op['channels'])==2
    assert len({x['channel_id'] for x in op['channels']})==1
    finish(c,p,a,op)
    runs=c.get(API+f"/agents/{a['id']}/workspace").json()['runs'];assert len(runs)==2
    assert len({r['source_id'] for r in runs})==2
    for r in runs:
        assert c.post(API+f"/agents/{a['id']}/runs/{r['id']}/playback").status_code==200
        refs=c.get(API+'/agent-services/references',params={'source_id':r['source_id']}).json()['items']
        assert refs[0]['active_run_ids']==[r['id']]
    for e in c.get(API+f"/agents/{a['id']}/events").json()['items']:
        assert c.get(API+f"/agents/{a['id']}/events/{e['id']}").status_code==200
    path=f"/agents/{a['id']}/channels/{runs[0]['channel_id']}/stop";key=str(uuid4())
    op=post(c,path,key=key).json();assert len(op['channels'])==2
    finish(c,p,a,op);assert post(c,path,key=key).json()['id']==op['id']
    assert all(r['state']=='stopped' for r in c.get(API+f"/agents/{a['id']}/workspace").json()['runs'])


def test_group_validation_checks_each_video_and_rejects_duplicate_bindings(demo):
    c,p,a,_,rev=grouped(demo)
    config=rev['config'];config['channels'][0]['sources'][1]['regions']=[]
    response=c.patch(API+f"/revisions/{rev['id']}",json={'config':config,'row_version':rev['row_version']});assert response.status_code==200
    value=post(c,f"/revisions/{rev['id']}/validations",{'row_version':response.json()['row_version']}).json()
    assert value['verdict']=='clarification_required' and value['missing_conditions']
    config['channels'][0]['sources'].append(config['channels'][0]['sources'][0])
    assert post(c,'/agents',{'name':'bad','config':config}).status_code==422


def test_group_apply_removal_stops_removed_source_and_retest_copies_only_baseline_source(demo):
    c,p,a,_,rev=grouped(demo);rev,_=publish(c,a);finish(c,p,a,submit(c,a,rev).json())
    runs=c.get(API+f"/agents/{a['id']}/workspace").json()['runs']
    clone=post(c,f"/agents/{a['id']}/revisions",{'base_revision_id':rev['id'],'row_version':detail(c,a)['row_version']}).json()
    clone['config']['channels'][0]['sources']=clone['config']['channels'][0]['sources'][:1]
    response=c.patch(API+f"/revisions/{clone['id']}",json={'config':clone['config'],'row_version':clone['row_version']});assert response.status_code==200
    newer,_=publish(c,a,clone['id']);op=submit(c,a,newer,kind='apply',run_ids=[r['id'] for r in runs]).json()
    assert finish(c,p,a,op)['state']=='succeeded'
    current=c.get(API+f"/agents/{a['id']}/workspace").json()['runs']
    assert sum(r['state']=='running' for r in current)==1
    baseline=runs[0]
    retest=post(c,f"/agents/{a['id']}/retests",{'baseline_run_id':baseline['id'],'row_version':detail(c,a)['row_version']}).json()
    assert len(retest['config']['channels'][0]['sources'])==1
    assert retest['config']['channels'][0]['sources'][0]['source_id']==baseline['source_id']
