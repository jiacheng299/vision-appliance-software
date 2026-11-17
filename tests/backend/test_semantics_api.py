"""时效画像与有效观察记录的接口契约。"""
import time

import pytest


@pytest.fixture
def seeded(app):
    from app.shared.models import Source
    from app.modules.agents.models import Agent
    with app.state.sessions() as db:
        db.add(Source(id='cam', name='摄像头', kind='camera', status='online',
                      width=960, height=540, fps=15.0))
        db.add(Agent(id='agent', name='任务', description='', owner_id='workspace'))
        db.commit()
    return app


GOOD_METRICS = dict(frame_count=30, duration_seconds=30.0, actual_fps=1.0, max_gap_seconds=1.1,
                    roi_visible_ratio=1.0, overexposure_ratio=0.05, blur_score=120.0,
                    occlusion_ratio=0.0, target_scale_px=40.0)
THRESHOLDS = dict(min_fps=0.9, max_gap_seconds=1.5, min_window_seconds=20.0,
                  min_roi_visible_ratio=0.9, max_overexposure_ratio=0.2,
                  min_blur_score=50.0, max_occlusion_ratio=0.3, min_target_scale_px=24.0)


def observation(source_id='cam', count=0, **overrides):
    payload = dict(source_id=source_id, task_key='person/absence', roi=[[0, 0], [1, 0], [1, 1], [0, 1]],
                   window_start=0.0, window_end=30.0, detection_count=count,
                   path_complete=True, metrics=dict(GOOD_METRICS), thresholds=dict(THRESHOLDS),
                   versions={'route_version': 'route-1', 'model_version': 'yolo11n'})
    payload.update(overrides)
    return payload


def test_profile_starts_empty_without_inventing_attributes(client, seeded):
    body = client.get('/api/v1/sources/cam/semantic-profile').json()
    assert body['version'] == 0 and body['attributes'] == []
    assert body['intrinsic'] == {} and body['runtime'] == {}


def test_intrinsic_update_bumps_version_and_rejects_unknown_keys(client, seeded):
    response = client.put('/api/v1/sources/cam/semantic-profile',
                          json={'values': {'resolution': '960x540', 'mount_position': '山地道路'}})
    assert response.status_code == 200
    body = response.json()
    assert body['version'] == 1 and body['intrinsic']['resolution'] == '960x540'
    bad = client.put('/api/v1/sources/cam/semantic-profile', json={'values': {'accuracy': '0.99'}})
    assert bad.status_code == 422
    assert bad.json()['error']['code'] == 'validation_error'


def test_attribute_upsert_requires_evidence_and_keeps_one_row_per_key(client, seeded):
    observed = time.time() - 5.0
    first = client.put('/api/v1/sources/cam/semantic-profile/attributes/lighting',
                       json={'value': {'label': 'strong_glare'}, 'source_kind': 'frame',
                             'observed_at': observed, 'source_frame_ts': 12.5,
                             'roi': [[0, 0], [0.5, 0], [0.5, 1], [0, 1]],
                             'confidence': 0.9, 'tau_seconds': 600.0,
                             'hard_expiry_at': observed + 3600.0})
    assert first.status_code == 200
    attribute = first.json()['attributes'][0]
    assert attribute['key'] == 'lighting' and attribute['source_kind'] == 'frame'
    assert attribute['state'] == 'valid' and attribute['usable'] is True
    assert attribute['source_frame_ts'] == 12.5
    second = client.put('/api/v1/sources/cam/semantic-profile/attributes/lighting',
                        json={'value': {'label': 'dim'}, 'source_kind': 'probe',
                              'observed_at': observed + 1.0, 'confidence': 0.4})
    views = second.json()['attributes']
    assert len(views) == 1 and views[0]['value']['label'] == 'dim'
    assert views[0]['version'] == 2


def test_attribute_validation_rejects_reversed_expiry_and_unsafe_keys(client, seeded):
    body = client.put('/api/v1/sources/cam/semantic-profile/attributes/weather',
                      json={'value': {'label': 'snow'}, 'source_kind': 'frame',
                            'observed_at': 500.0, 'hard_expiry_at': 400.0})
    assert body.status_code == 422
    unsafe = client.put('/api/v1/sources/cam/semantic-profile/attributes/bad key',
                        json={'value': {'label': 'snow'}, 'source_kind': 'frame'})
    assert unsafe.status_code == 422
    assert unsafe.json()['error']['code'] == 'attribute_key_invalid'
    outside = client.put('/api/v1/sources/cam/semantic-profile/attributes/weather',
                         json={'value': {'label': 'snow'}, 'source_kind': 'frame',
                               'roi': [[0, 0], [2, 0], [1, 1]]})
    assert outside.status_code == 422


def test_expired_attribute_reads_as_unknown_and_never_as_the_opposite(client, seeded):
    client.put('/api/v1/sources/cam/semantic-profile/attributes/lighting',
               json={'value': {'label': 'strong_glare'}, 'source_kind': 'frame',
                     'observed_at': 1_000.0, 'confidence': 0.9, 'tau_seconds': 60.0,
                     'hard_expiry_at': 1_500.0})
    later = client.get('/api/v1/sources/cam/semantic-profile', params={'at': 1_600.0}).json()
    attribute = later['attributes'][0]
    assert attribute['state'] == 'expired'
    assert attribute['strength'] == 0.0
    assert attribute['usable'] is False
    assert attribute['value']['label'] == 'strong_glare'
    earlier = client.get('/api/v1/sources/cam/semantic-profile', params={'at': 900.0}).json()
    assert earlier['attributes'][0]['state'] == 'unknown'
    assert earlier['attributes'][0]['reason'] == 'timestamp_before_observation'


def test_observation_post_returns_the_three_states(client, seeded):
    detected = client.post('/api/v1/agents/agent/observations', json=observation(count=2))
    assert detected.status_code == 201 and detected.json()['verdict'] == 'detected'
    empty = client.post('/api/v1/agents/agent/observations', json=observation(count=0))
    assert empty.json()['verdict'] == 'not_detected'
    blocked_metrics = dict(GOOD_METRICS, overexposure_ratio=0.6)
    blocked = client.post('/api/v1/agents/agent/observations',
                          json=observation(count=0, metrics=blocked_metrics))
    assert blocked.json()['verdict'] == 'insufficient'
    assert any('过曝' in reason for reason in blocked.json()['reasons'])


def test_stale_profile_version_is_refused_even_without_expectations(client, seeded):
    client.put('/api/v1/sources/cam/semantic-profile', json={'values': {'resolution': '960x540'}})
    payload = observation(count=1)
    payload['versions'] = {'route_version': 'route-1', 'model_version': 'yolo11n',
                           'profile_version': 99}
    result = client.post('/api/v1/agents/agent/observations', json=payload).json()
    assert result['verdict'] == 'insufficient'
    assert any('版本' in reason for reason in result['reasons'])


def test_observation_list_filters_paginates_and_counts(client, seeded):
    for index in range(5):
        client.post('/api/v1/agents/agent/observations',
                    json=observation(count=index % 2, window_start=float(index * 30),
                                     window_end=float(index * 30 + 30)))
    page = client.get('/api/v1/agents/agent/observations', params={'limit': 2}).json()
    assert len(page['items']) == 2 and page['next_cursor']
    assert page['summary'].get('detected', 0) + page['summary'].get('not_detected', 0) == 5
    rest = client.get('/api/v1/agents/agent/observations',
                      params={'limit': 2, 'cursor': page['next_cursor']}).json()
    assert {item['id'] for item in rest['items']} & {item['id'] for item in page['items']} == set()
    filtered = client.get('/api/v1/agents/agent/observations',
                          params={'verdict': 'not_detected'}).json()
    assert filtered['items'] and all(item['verdict'] == 'not_detected' for item in filtered['items'])
    tampered = client.get('/api/v1/agents/agent/observations',
                          params={'limit': 2, 'cursor': 'deadbeef:1'})
    assert tampered.status_code == 422


def test_unknown_source_or_agent_is_reported_not_created(client, seeded):
    assert client.get('/api/v1/sources/missing/semantic-profile').status_code == 404
    orphan = client.post('/api/v1/agents/agent/observations',
                         json=observation(source_id='missing'))
    assert orphan.status_code == 404
    assert client.post('/api/v1/agents/missing/observations',
                       json=observation()).status_code == 404
    assert client.get('/api/v1/sources/missing/semantic-profile',
                      params={'at': 1.0}).status_code == 404
