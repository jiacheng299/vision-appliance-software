"""影子运行的资源实测：如实报告可用性、边际内存与预算判定。"""
from pathlib import Path

import pytest

from app.modules.routing import preheat

REPO_MODEL = Path(__file__).resolve().parents[2] / 'var/models/yolo11n/yolo11n.onnx'


def test_a_missing_artifact_is_reported_rather_than_guessed(tmp_path):
    measurement = preheat.measure(tmp_path / 'nope.onnx', frames=3)
    assert measurement.available is False
    assert '模型文件不可读' in measurement.reason
    assert measurement.rss_delta_mb is None


def test_an_empty_artifact_is_refused(tmp_path):
    broken = tmp_path / 'empty.onnx'
    broken.write_bytes(b'')
    measurement = preheat.measure(broken, frames=2)
    assert measurement.available is False


def measurement_of(**overrides):
    base = dict(available=True, reason=None, model_path='m.onnx', frames=5,
                load_ms=90.0, baseline_ms=60.0, shadow_ms=62.0, latency_delta_ms=2.0,
                rss_delta_mb=85.0, rss_total_mb=180.0)
    base.update(overrides)
    return preheat.PreheatMeasurement(**base)


def test_budget_check_reports_both_dimensions():
    fits = preheat.budget_check(measurement_of(), budgets_cpu_ms=200.0, budgets_memory_mb=1024.0)
    assert fits['fits'] is True
    heavy = preheat.budget_check(measurement_of(rss_delta_mb=2048.0), budgets_cpu_ms=200.0,
                                 budgets_memory_mb=1024.0)
    assert heavy['fits'] is False and '内存增量' in heavy['reason']
    slow = preheat.budget_check(measurement_of(shadow_ms=500.0), budgets_cpu_ms=200.0,
                                budgets_memory_mb=1024.0)
    assert slow['fits'] is False and '单帧耗时' in slow['reason']
    unknown = preheat.budget_check(measurement_of(available=False, reason='无模型'),
                                   budgets_cpu_ms=200.0, budgets_memory_mb=1024.0)
    assert unknown['fits'] is None and unknown['reason'] == '无模型'


@pytest.mark.skipif(not REPO_MODEL.is_file(), reason='本机没有可信 ONNX 模型')
def test_a_real_second_session_costs_a_measurable_amount_of_memory():
    measurement = preheat.measure(REPO_MODEL, frames=3)
    assert measurement.available is True, measurement.reason
    assert measurement.load_ms is not None and measurement.load_ms > 0
    assert measurement.rss_delta_mb is not None and measurement.rss_delta_mb > 0
    assert measurement.rss_total_mb >= measurement.rss_delta_mb
    assert any('同一份 ONNX' in note for note in measurement.notes)


def test_the_endpoint_states_clearly_when_the_artifact_is_absent(app, client):
    response = client.post('/api/v1/routing/preheat', params={'frames': 2})
    assert response.status_code == 200
    body = response.json()
    assert body['available'] is False            # 临时数据目录里没有模型
    assert '模型文件不可读' in body['reason']
    assert body['budget']['fits'] is None
    assert body['budgets']['memory_mb'] == 1024.0
