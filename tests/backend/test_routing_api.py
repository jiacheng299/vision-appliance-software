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
