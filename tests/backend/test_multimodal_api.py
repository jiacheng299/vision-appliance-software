import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.agents.contracts import CapabilityCatalog, CapabilityItem
from app.modules.agents.schemas import CapabilityRef
from app.modules.agents.schemas import ChannelConfig
from app.modules.models.multimodal_api import MultimodalApiClient, MultimodalFrame
from app.shared.config import Config
from app.shared.errors import Error


def configured(tmp_path, **changes):
    values = dict(
        var_root=tmp_path,
        multimodal_api_url='https://vision.example/v1/chat/completions',
        multimodal_api_key='private-api-key',
        multimodal_model='vision-test-1',
    )
    values.update(changes)
    config = Config(**values)
    config.prepare()
    return config


def answer(value, status=200):
    return httpx.Response(status, json={'choices': [{'message': {'content': json.dumps(value, ensure_ascii=False)}}]})


def test_unconfigured_api_is_not_advertised_and_fails_closed(tmp_path):
    client = MultimodalApiClient(Config(var_root=tmp_path))
    assert client.deployment() is None
    with pytest.raises(Error) as caught:
        client.plan(ChannelConfig(name='监测任务', requirement_text='检测人员是否睡着'), [])
    assert caught.value.status == 503 and caught.value.code == 'multimodal_api_not_configured'


def test_remote_api_requires_https_and_key_while_loopback_can_be_keyless(tmp_path):
    assert MultimodalApiClient(configured(tmp_path, multimodal_api_url='http://vision.example/v1/chat/completions')).deployment() is None
    assert MultimodalApiClient(configured(tmp_path, multimodal_api_key=None)).deployment() is None
    local = configured(tmp_path, multimodal_api_url='http://127.0.0.1:11434/v1/chat/completions', multimodal_api_key=None)
    assert MultimodalApiClient(local).deployment().health == 'healthy'


def test_planning_uses_full_requirement_but_never_sends_source_ids_or_secret(tmp_path):
    requirement = '检测值班人员是否睡着，连续 30 秒后报警'
    captured = {}
    def handler(request):
        captured['request'] = request
        captured['body'] = json.loads(request.content)
        return answer({
            'target': 'visual_subject',
            'rule': 'multimodal_observation',
            'instruction': requirement,
            'duration_seconds': 30,
            'requires_region': True,
            'requires_duration': True,
            'verdict': 'executable',
            'missing_conditions': [],
            'limitations': ['API 模型结果需要现场验证。'],
        })
    client = MultimodalApiClient(configured(tmp_path), transport=httpx.MockTransport(handler))
    channel = ChannelConfig(name='监测任务', requirement_text=requirement, task_mode='natural_language')
    result = client.plan(channel, [{'id':'private-camera-id','kind':'camera','duration_ms':None}])
    assert result.instruction == requirement and result.verdict == 'executable'
    request, body = captured['request'], captured['body']
    assert request.headers['Authorization'] == 'Bearer private-api-key'
    encoded = json.dumps(body, ensure_ascii=False)
    assert requirement in encoded
    assert 'private-camera-id' not in encoded and 'private-api-key' not in encoded
    assert body['model'] == 'vision-test-1' and body['response_format'] == {'type':'json_object'}


def test_frame_analysis_sends_bounded_jpegs_and_returns_structured_decision(tmp_path):
    captured = {}
    def handler(request):
        captured['body'] = json.loads(request.content)
        return answer({'triggered': True, 'confidence': .91, 'event_type': 'sleeping_on_duty',
                       'reason': '值班人员头部持续伏在桌面。', 'observed_timestamp_ms': 2000})
    client = MultimodalApiClient(configured(tmp_path), transport=httpx.MockTransport(handler))
    frames = [MultimodalFrame(timestamp_ms=value, jpeg=b'\xff\xd8frame\xff\xd9') for value in (1000, 2000)]
    result = client.analyze_frames('检测值班人员是否睡着', frames)
    assert result.triggered and result.event_type == 'sleeping_on_duty' and result.confidence == .91
    content = captured['body']['messages'][1]['content']
    assert content[0]['type'] == 'text'
    assert [item['type'] for item in content[1:]] == ['image_url','image_url']
    assert all(item['image_url']['url'].startswith('data:image/jpeg;base64,') for item in content[1:])


def test_template_match_can_only_select_a_server_supplied_candidate(tmp_path):
    reference = CapabilityRef(model_id='model',model_version='1',template_id='template',template_version='1')
    catalog = CapabilityCatalog(items=[CapabilityItem(name='人员区域入侵',reference=reference,
        targets=['person'],rules=['intrusion'],requires_region=['intrusion'],requires_duration=['intrusion'])],
        fingerprint='catalog',data_origin='real')
    client = MultimodalApiClient(configured(tmp_path),transport=httpx.MockTransport(lambda request: answer({
        'status':'matched','candidate_index':0,'target':'person','rule':'intrusion','duration_seconds':8,
        'confidence':.95,'covers_all_requirements':True})))
    result = client.match_template('人员进入区域持续 8 秒报警',catalog)
    assert result.capability_ref == reference and result.duration_seconds == 8


@pytest.mark.parametrize('response', [
    httpx.Response(302, headers={'Location':'https://attacker.invalid/'}),
    httpx.Response(200, content=b'x' * 70000),
    httpx.Response(200, json={'choices': []}),
])
def test_bad_upstream_responses_fail_without_leaking_details(tmp_path, response):
    client = MultimodalApiClient(configured(tmp_path), transport=httpx.MockTransport(lambda request: response))
    with pytest.raises(Error) as caught:
        client.plan(ChannelConfig(name='监测任务', requirement_text='检测火情', task_mode='natural_language'), [])
    assert caught.value.status == 502 and caught.value.code == 'multimodal_api_invalid_response'
    assert 'attacker' not in caught.value.message


def test_planning_rejects_provider_invented_executor_rules(tmp_path):
    client = MultimodalApiClient(configured(tmp_path), transport=httpx.MockTransport(lambda request: answer({
        'target': 'shell', 'rule': 'run_command', 'instruction': '检测火情',
        'duration_seconds': None, 'requires_region': False, 'requires_duration': False,
        'verdict': 'executable', 'missing_conditions': [], 'limitations': [],
    })))
    with pytest.raises(Error) as caught:
        client.plan(ChannelConfig(name='监测任务', requirement_text='检测火情', task_mode='natural_language'), [])
    assert caught.value.status == 502 and caught.value.code == 'multimodal_api_invalid_response'


def test_frame_limits_and_jpeg_validation_are_enforced_before_network(tmp_path):
    called = False
    def handler(request):
        nonlocal called
        called = True
        return answer({})
    config = configured(tmp_path, multimodal_max_frames=2)
    client = MultimodalApiClient(config, transport=httpx.MockTransport(handler))
    with pytest.raises(Error) as caught:
        client.analyze_frames('检测火情', [MultimodalFrame(timestamp_ms=0, jpeg=b'not-jpeg')])
    assert caught.value.status == 422
    valid = MultimodalFrame(timestamp_ms=0, jpeg=b'\xff\xd8x\xff\xd9')
    with pytest.raises(Error) as caught:
        client.analyze_frames('检测火情', [valid, valid, valid])
    assert caught.value.status == 422 and not called


def test_configured_adapter_is_selectable_and_plans_the_no_template_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv('VISION_MULTIMODAL_API_URL','http://127.0.0.1:11434/v1/chat/completions')
    monkeypatch.setenv('VISION_MULTIMODAL_MODEL','local-vision')
    app=create_app(var_root=tmp_path,testing=True)
    app.state.model_services.multimodal_api.transport=httpx.MockTransport(lambda request: answer({
        'target':'visual_subject','rule':'multimodal_observation','instruction':'检测值班人员是否睡着',
        'duration_seconds':None,'requires_region':False,'requires_duration':False,'verdict':'executable',
        'missing_conditions':[],'limitations':['需要现场验证。']}))
    with TestClient(app) as client:
        page=client.get('/api/v1/llm/deployments').json()
        deployment=page['items'][0]
        selection=next(item for item in page['selections'] if item['usage']=='multimodal_analysis')
        selected=client.put('/api/v1/llm/selections/multimodal_analysis',json={
            'deployment_id':deployment['id'],'row_version':selection['row_version']})
        assert selected.status_code==200,selected.text
        response=client.post('/api/v1/requirements/plan',json={'channel':{
            'name':'睡岗监测','task_mode':'natural_language','requirement_text':'检测值班人员是否睡着'}})
        assert response.status_code==200,response.text
        result=response.json()
        assert result['strategy']=='multimodal'
        assert result['channel']['execution_plan']['deployment_id']==deployment['id']
        assert result['verdict']=='clarification_required'  # A video source is still required before execution.
