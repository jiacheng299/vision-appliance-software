"""追踪策略状态接口：配置里写的是什么，实际装载出来的是什么。"""
import sys
import types

import pytest

from app.modules.tracking import registry


@pytest.fixture(autouse=True)
def clear_cache():
    registry.forget()
    yield
    registry.forget()


@pytest.fixture
def plugin(monkeypatch):
    module = types.ModuleType('tests_status_policy')

    class Policy:
        name = 'fake-external'
        track_prefix = 'x'

        def reset(self):
            pass

        def decide(self, observation, tracks):
            from app.modules.tracking.policy import Decision
            return Decision()

        def describe(self):
            return {'name': self.name, 'kind': 'learned', 'weights': 'v1'}

    module.Policy = Policy
    monkeypatch.setitem(sys.modules, 'tests_status_policy', module)
    return module


def read(client):
    response = client.get('/api/v1/tracking/policies')
    assert response.status_code == 200, response.text
    return response.json()


def test_the_default_configuration_reports_the_builtin_policy_as_active(app, client):
    body = read(client)
    assert body['active'] == 'heuristic-iou'
    assert body['resolved']['available'] is True
    assert body['resolved']['name'] == 'heuristic-iou'
    assert body['resolved']['external'] is False
    assert '内置策略 heuristic-iou' in body['notice']


def test_the_catalogue_still_lists_the_uninstalled_marl_slot(app, client):
    body = read(client)
    entries = {item['name']: item for item in body['items']}
    assert entries['heuristic-iou']['installed'] is True
    assert entries['marl-association']['installed'] is False


def test_an_uninstalled_slot_is_reported_as_unavailable_not_silently_replaced(app, client):
    app.state.config.tracker_policy = 'marl-association'
    body = read(client)
    assert body['active'] == 'marl-association'
    assert body['resolved']['available'] is False
    assert '尚未安装' in body['resolved']['reason']
    assert '当前不可用' in body['notice']
    # 目录仍然完整，用户能看到还有哪些策略存在
    assert any(item['name'] == 'heuristic-iou' for item in body['items'])


def test_an_external_policy_is_reported_as_external_with_its_description(app, client, plugin):
    app.state.config.tracker_policy = 'tests_status_policy:Policy'
    body = read(client)
    assert body['resolved']['available'] is True
    assert body['resolved']['external'] is True
    assert body['resolved']['name'] == 'fake-external'
    assert body['resolved']['detail']['weights'] == 'v1'
    assert '外部追踪策略 fake-external' in body['notice']


def test_a_broken_external_spec_is_reported_with_its_reason(app, client):
    app.state.config.tracker_policy = 'tests_missing_module:Policy'
    body = read(client)
    assert body['resolved']['available'] is False
    assert body['resolved']['external'] is True
    assert '无法导入' in body['resolved']['reason']


def test_the_description_is_cached_per_process(app, client, plugin):
    app.state.config.tracker_policy = 'tests_status_policy:Policy'
    first = read(client)['resolved']
    calls = []

    original = registry._external

    def counting(spec):
        calls.append(spec)
        return original(spec)

    registry._external = counting
    try:
        second = read(client)['resolved']
    finally:
        registry._external = original
    assert first == second
    assert calls == []          # 第二次请求命中缓存，不再构造策略
