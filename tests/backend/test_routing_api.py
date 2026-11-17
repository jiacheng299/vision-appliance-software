"""路由评估接口：画像现状如何改变候选组合与可行性。"""
import time

import pytest


@pytest.fixture
def seeded(app):
    from app.shared.models import Source
    with app.state.sessions() as db:
        db.add(Source(id='cam', name='摄像头', kind='camera', status='online',
                      width=960, height=540, fps=15.0))
        db.commit()
    return app


def routes(client, **params):
    response = client.get('/api/v1/sources/cam/routes', params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_clear_scene_selects_the_only_installed_detector(client, seeded):
    body = routes(client, rule='absence')
    assert body['chosen']['members'] == ['yolo11n-person']
    assert body['chosen']['feasible'] is True
    assert body['chosen']['score'] > 1.0
    assert body['scenario']['bucket'] == 'default'
    assert [item['key'] for item in body['graph']['requirements']] == ['person_detect']
    assert body['weights']['alpha'] == 1.0


def test_the_response_admits_which_numbers_are_uncalibrated(client, seeded):
    body = routes(client, rule='absence')
    assert any('未做分桶验证' in notice for notice in body['notices'])
    uncalibrated = [item['id'] for item in body['capabilities'] if not item['calibrated']]
    assert 'yolo11n-person' in uncalibrated
    assert any('观察记录' in notice for notice in body['notices'])


def test_a_glare_attribute_switches_bucket_and_blocks_every_route(client, seeded):
    observed = time.time() - 1.0
    response = client.put('/api/v1/sources/cam/semantic-profile/attributes/lighting',
                          json={'value': {'label': 'strong_glare'}, 'source_kind': 'frame',
                                'observed_at': observed, 'confidence': 0.8,
                                'hard_expiry_at': observed + 3600.0})
    assert response.status_code == 200
    body = routes(client, rule='absence')
    assert body['scenario']['bucket'] == 'glare'
    assert body['chosen'] is None
    reasons = [reason for item in body['blocked'] for reason in item['reasons']]
    assert any('低于必需质量' in reason for reason in reasons)
    assert any('未安装' in reason for reason in reasons)


def test_provider_context_does_not_change_present_absence_of_a_calibrated_floor(client, seeded):
    relaxed = routes(client, rule='absence', min_quality=0.0)
    assert relaxed['min_quality'] == 0.0
    assert relaxed['chosen'] is not None
    strict = routes(client, rule='absence', min_quality=0.95)
    assert strict['chosen'] is None
    assert strict['min_quality'] == 0.95


def test_intrusion_requires_detector_tracker_and_zone_rule(client, seeded):
    body = routes(client, rule='intrusion', duration_seconds=8)
    assert set(body['chosen']['members']) == {'yolo11n-person', 'heuristic-tracker', 'zone-rule'}
    assert body['chosen']['dependency'] == 1.0
    edges = {edge['kind']: edge for edge in body['graph']['edges']}
    assert edges['temporal']['seconds'] == 8.0
    assert edges['serial']['source'] == 'person_detect'


def test_unknown_source_and_invalid_rule_are_rejected(client, seeded):
    assert client.get('/api/v1/sources/missing/routes').status_code == 404
    assert client.get('/api/v1/sources/cam/routes',
                      params={'rule': 'crowd_density'}).status_code == 422
    assert client.get('/api/v1/sources/cam/routes',
                      params={'rule': 'absence', 'min_quality': 2}).status_code == 422


def test_route_evidence_points_at_the_window_it_used(client, seeded):
    """有观察记录时，路由评估应指出场景证据来自哪一窗、那一窗是否有效。"""
    payload = dict(source_id='cam', task_key='person/absence',
                   roi=[[0, 0], [1, 0], [1, 1], [0, 1]], window_start=0.0, window_end=30.0,
                   detection_count=0, path_complete=True,
                   metrics=dict(frame_count=30, duration_seconds=30.0, actual_fps=1.0,
                                max_gap_seconds=1.1, roi_visible_ratio=1.0,
                                overexposure_ratio=0.05, blur_score=120.0,
                                occlusion_ratio=0.0, target_scale_px=64.0),
                   thresholds=dict(min_fps=0.9, max_gap_seconds=1.5, min_window_seconds=20.0,
                                   min_roi_visible_ratio=0.9, max_overexposure_ratio=0.2,
                                   min_blur_score=50.0, max_occlusion_ratio=0.3,
                                   min_target_scale_px=24.0),
                   versions={'route_version': 'route-1', 'model_version': 'yolo11n'})
    with seeded.state.sessions() as db:
        from app.modules.agents.models import Agent
        db.add(Agent(id='agent', name='任务', description='', owner_id='workspace'))
        db.commit()
    created = client.post('/api/v1/agents/agent/observations', json=payload)
    assert created.status_code == 201
    observation_id = created.json()['id']

    body = routes(client, rule='absence')
    assert body['evidence']['observation_id'] == observation_id
    assert body['evidence']['verdict'] == 'not_detected'
    assert body['evidence']['usable'] is True
    assert body['scenario']['target_px'] == 64.0
    assert not any('观察不足' in notice and '只能作为提示' in notice for notice in body['notices'])


def test_an_insufficient_window_is_flagged_as_a_hint_not_evidence(client, seeded):
    payload = dict(source_id='cam', task_key='person/absence', roi=[], window_start=0.0,
                   window_end=30.0, detection_count=0, path_complete=True,
                   metrics=dict(frame_count=30, duration_seconds=30.0, actual_fps=1.0,
                                max_gap_seconds=1.1, roi_visible_ratio=1.0,
                                overexposure_ratio=0.62, blur_score=120.0,
                                occlusion_ratio=0.0, target_scale_px=64.0),
                   thresholds=dict(min_fps=0.9, max_gap_seconds=1.5, min_window_seconds=20.0,
                                   min_roi_visible_ratio=0.9, max_overexposure_ratio=0.2,
                                   min_blur_score=50.0, max_occlusion_ratio=0.3,
                                   min_target_scale_px=24.0),
                   versions={'route_version': 'route-1', 'model_version': 'yolo11n'})
    with seeded.state.sessions() as db:
        from app.modules.agents.models import Agent
        db.add(Agent(id='agent', name='任务', description='', owner_id='workspace'))
        db.commit()
    created = client.post('/api/v1/agents/agent/observations', json=payload)
    assert created.json()['verdict'] == 'insufficient'

    body = routes(client, rule='absence')
    assert body['evidence']['verdict'] == 'insufficient'
    assert body['evidence']['usable'] is False
    assert any('只能作为提示' in notice for notice in body['notices'])


def test_without_any_observation_the_route_says_so(client, seeded):
    body = routes(client, rule='absence')
    assert body['evidence'] is None
    assert any('还没有观察记录' in notice for notice in body['notices'])