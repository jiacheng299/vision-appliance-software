from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

API='/api/v1'
def post(c,path,body,key=None):
    return c.post(API+path,json=body,headers={'Idempotency-Key':key or str(uuid4())})

@pytest.fixture
def templates(tmp_path,monkeypatch):
    monkeypatch.setenv('VISION_AGENT_DEMO','true')
    from app.main import create_app
    app=create_app(var_root=tmp_path,testing=True)
    with TestClient(app) as c:
        ref=next(i['reference'] for i in c.get(API+'/agent-services/capabilities').json()['items'] if 'fire' in i['targets'])
        source=post(c,'/sources',{'kind':'camera','name':'验收直播','address':'rtsp://127.0.0.1/live'}).json()['id']
        yield c,app,ref,source

def make(c,ref,parameters=None,key=None):
    r=post(c,'/agent-templates',{'name':'火灾检测','config':{'model_ref':ref,'parameters':parameters or []}},key)
    assert r.status_code==201,r.text
    return r.json()

def publish(c,t,key=None):
    r=post(c,f'/agent-templates/{t["id"]}/publish',{'row_version':t['row_version'],'revision_id':t['latest_revision']['id']},key)
    assert r.status_code==200,r.text
    return r.json()

def task(c,t,source,parameters=None,key=None):
    return post(c,f'/agent-templates/{t["id"]}/tasks',{'name':'仓库任务','template_revision_id':t['published_revision']['id'],'source':{'source_id':source},'parameters':parameters or []},key)

def test_developer_option_pool_is_read_only_and_typed(templates):
    c,_,ref,_=templates
    catalog=c.get(API+'/agent-parameter-options').json()
    assert catalog['editable_by_user'] is False and len(catalog['items'])>=20
    assert {'target','rule','confidence_threshold','working_hours','require_tracking'} <= {i['key'] for i in catalog['items']}
    assert post(c,'/agent-parameter-options',{'key':'invented'}).status_code==405
    for parameters in [[{'key':'invented','value':1}],[{'key':'confidence_threshold','value':1.1}],[{'key':'min_count','value':True}],
                       [{'key':'color','value':'ultraviolet'}],[{'key':'working_hours','value':'25:00-30:00'}],
                       [{'key':'min_count','value':5},{'key':'max_count','value':1}],
                       [{'key':'target','value':'fire'},{'key':'target','value':'smoke'}]]:
        r=post(c,'/agent-templates',{'name':'invalid','config':{'model_ref':ref,'parameters':parameters}})
        assert r.status_code==422,r.text

def test_template_creation_publish_and_task_instantiation_are_idempotent(templates):
    c,_,ref,source=templates
    key=str(uuid4());t=make(c,ref,key=key);assert make(c,ref,key=key)==t
    publish_key=str(uuid4());published=publish(c,t,publish_key);assert publish(c,t,publish_key)==published
    task_key=str(uuid4());first=task(c,published,source,key=task_key);second=task(c,published,source,key=task_key)
    assert first.status_code==second.status_code==201,(first.text,second.text)
    assert first.json()==second.json()
    data=first.json();config=data['latest_revision']['config']
    assert config['agent_template_ref']['revision_id']==published['published_revision']['id']
    assert config['channels'][0]['capability_ref']==ref
    card=c.get(API+'/agent-templates/'+t['id']).json()
    assert card['task_count']==card['source_count']==1
    rows=c.get(API+f'/agent-templates/{t["id"]}/tasks').json()['items']
    assert rows[0]['agent']['id']==data['id'] and rows[0]['sources'][0]['id']==source
    sources=c.get(API+f'/agent-templates/{t["id"]}/sources').json()['items']
    assert [s['id'] for s in sources]==[source]
    references=c.get(API+'/agent-services/references',params={'model_id':ref['model_id'],'model_version':ref['model_version']}).json()['items']
    assert any(i['reference_kind']=='template' and i['agent_id']==t['id'] for i in references)
    assert any(i['reference_kind']=='agent' and i['agent_id']==data['id'] for i in references)

def test_template_changes_never_rewrite_existing_tasks(templates):
    c,_,ref,source=templates
    old=publish(c,make(c,ref,[{'key':'confidence_threshold','value':.7}]))
    first=task(c,old,source).json();before=c.get(API+'/agents/'+first['id']).json()['latest_revision']['config']
    changed=c.patch(API+'/agent-templates/'+old['id'],json={'name':'新版火灾检测','description':'新版条件','row_version':old['row_version'],
        'config':{'model_ref':ref,'parameters':[{'key':'confidence_threshold','value':.9}]}})
    assert changed.status_code==200,changed.text
    draft=changed.json();assert draft['latest_revision']['revision_no']==2 and draft['published_revision']['revision_no']==1
    new=publish(c,draft);second=task(c,new,source).json()
    after=c.get(API+'/agents/'+first['id']).json()['latest_revision']['config']
    assert before==after
    assert before['channels'][0]['parameters'][0]['value']==.7
    assert second['latest_revision']['config']['channels'][0]['parameters'][0]['value']==.9
    assert second['latest_revision']['config']['agent_template_ref']['revision_no']==2
    old_replay=task(c,old,source).json()['latest_revision']['config']
    assert old_replay['agent_template_ref']['name']=='火灾检测'

def test_tasks_cannot_forge_template_version_model_or_parameter_pool(templates):
    c,_,ref,source=templates
    t=publish(c,make(c,ref,[{'key':'min_count','required':True}]))
    assert task(c,t,source).status_code==422
    assert task(c,t,source,[{'key':'color','value':'red'}]).status_code==422
    r=task(c,t,source,[{'key':'min_count','value':1}]);assert r.status_code==201,r.text
    config=r.json()['latest_revision']['config'];revision=r.json()['latest_revision']
    import copy
    for mutate in [lambda x:x['agent_template_ref'].update(revision_no=99),lambda x:x['channels'][0]['capability_ref'].update(model_id='forged'),
                   lambda x:x['channels'][0]['parameters'].append({'key':'color','value':'red'}),lambda x:x.update(agent_template_ref=None),
                   lambda x:x['channels'][0]['parameters'][0].update(required=False),
                   lambda x:x['channels'][0].update(task_mode='natural_language'),
                   lambda x:x['channels'][0].update(execution_plan={'plan_id':'forged','executor_kind':'multimodal','deployment_id':'other','deployment_version':'1','instruction':'different task','reason':'forged'})]:
        altered=copy.deepcopy(config);mutate(altered)
        response=c.patch(API+'/revisions/'+revision['id'],json={'row_version':revision['row_version'],'config':altered})
        assert response.status_code==422,response.text
    assert post(c,'/agents',{'name':'forged','config':config}).status_code==422

def test_archiving_template_keeps_old_tasks_and_versions(templates):
    c,_,ref,source=templates
    t=publish(c,make(c,ref));key=str(uuid4());created=task(c,t,source,key=key).json()
    archived=post(c,f'/agent-templates/{t["id"]}/archive',{'row_version':t['row_version'],'archived':True})
    assert archived.status_code==200
    assert task(c,t,source).status_code==409
    assert task(c,t,source,key=key).json()==created
    assert c.get(API+'/agents/'+created['id']).status_code==200
    assert c.get(API+f'/agent-templates/{t["id"]}/tasks').json()['items'][0]['agent']['id']==created['id']

def test_declared_parameters_are_preserved_through_validation_and_runtime(templates):
    c,app,ref,source=templates
    t=publish(c,make(c,ref,[{'key':'confidence_threshold','value':.85}]))
    result=task(c,t,source).json();revision=result['latest_revision']
    validation=post(c,f'/revisions/{revision["id"]}/validations',{'row_version':revision['row_version']})
    assert validation.status_code==201,validation.text
    v=validation.json();assert v['verdict']=='executable',v
    revision=c.get(API+'/revisions/'+revision['id']).json()
    confirmed=post(c,f'/revisions/{revision["id"]}/confirmations',{'row_version':revision['row_version'],'validation_id':v['id'],'config_hash':v['config_hash'],'limitations_acknowledged':True})
    assert confirmed.status_code==200,confirmed.text
    channel=confirmed.json()['config']['channels'][0]
    start=post(c,f'/agents/{result["id"]}/run-groups',{'revision_id':revision['id'],'channel_ids':[channel['channel_id']],'expected_active_run_ids':[]})
    assert start.status_code==202,start.text
    app.state.agent_services.advance(5)
    runs=c.get(API+f'/agents/{result["id"]}/workspace').json()['runs']
    assert runs[0]['config_snapshot']['channels'][0]['parameters'][0]['value']==.85

def test_unknown_parameter_support_fails_closed(templates):
    c,app,ref,source=templates
    t=publish(c,make(c,ref,[{'key':'color','value':'red'}]))
    result=task(c,t,source).json();r=result['latest_revision']
    app.state.agent_services.supports_configurable_parameters=False
    response=post(c,f'/revisions/{r["id"]}/validations',{'row_version':r['row_version']})
    assert response.status_code==503,response.text


def test_model_must_explicitly_declare_parameter_support(templates,monkeypatch):
    c,app,ref,source=templates
    t=publish(c,make(c,ref,[{'key':'color','value':'red'}]))
    result=task(c,t,source).json();r=result['latest_revision']
    original=app.state.agent_services.catalog
    def without_color(actor):
        catalog=original(actor)
        for item in catalog.items: item.parameter_keys=[]
        return catalog
    monkeypatch.setattr(app.state.agent_services,'catalog',without_color)
    response=post(c,f'/revisions/{r["id"]}/validations',{'row_version':r['row_version']})
    assert response.status_code==201,response.text
    validation=response.json()
    assert validation['verdict']=='unsupported'
    assert any('目标颜色' in message for message in validation['unsupported_conditions'])


def test_model_references_paginate_templates_and_tasks_without_omission(templates):
    c,_,ref,source=templates
    for _ in range(3):
        t=publish(c,make(c,ref));assert task(c,t,source).status_code==201
    parameters={'model_id':ref['model_id'],'model_version':ref['model_version'],'limit':1}
    seen=[]
    while True:
        response=c.get(API+'/agent-services/references',params=parameters)
        assert response.status_code==200,response.text
        page=response.json();seen.extend((row['reference_kind'],row['revision_id']) for row in page['items'])
        if not page['next_cursor']: break
        parameters['cursor']=page['next_cursor']
        assert len(seen)<10
    assert len(seen)==len(set(seen))==6
    assert {kind for kind,_ in seen}=={'agent','template'}
