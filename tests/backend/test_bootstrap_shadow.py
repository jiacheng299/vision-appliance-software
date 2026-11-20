"""首次运行的画像初始化与影子对照：只填缺项、只报实测。"""
import numpy as np
import pytest

from app.modules.routing import shadow
from app.modules.semantics import bootstrap as bootstrap_module
from app.modules.semantics import service as semantics


@pytest.fixture
def seeded(app):
    from app.shared.models import Source
    with app.state.sessions() as db:
        db.add(Source(id='cam', name='摄像头', kind='camera', status='online',
                      width=960, height=540, fps=15.0))
        db.add(Source(id='rec', name='录像', kind='file', status='ready',
                      width=640, height=480, duration_ms=8000, media_key='sample.mp4'))
        db.commit()
    return app


def test_intrinsic_uses_the_device_record_and_never_the_address():
    from types import SimpleNamespace
    source = SimpleNamespace(id='cam', kind='camera', width=960, height=540,
                             address='rtsp://user:secret@10.0.0.9/live')
    values = bootstrap_module.intrinsic_from(source)
    assert values == {'device_id': 'cam', 'stream': 'camera', 'resolution': '960x540'}
    assert not any('secret' in str(value) or '10.0.0.9' in str(value) for value in values.values())


def test_brightness_labels_are_deliberately_coarse():
    assert bootstrap_module.lighting_label(0.05) == 'low_light'
    assert bootstrap_module.lighting_label(0.95) == 'bright_light'
    assert bootstrap_module.lighting_label(0.5) == 'daylight'


def test_a_camera_source_gets_intrinsic_only_and_says_why(seeded):
    with seeded.state.sessions() as db:
        result = bootstrap_module.bootstrap(db, 'cam')
        db.commit()
    # 分辨率在读取画像时已自动写入；bootstrap 只补其余设备字段。
    assert result['profile'].intrinsic['resolution'] == '960x540'
    assert any('device_id' in item for item in result['created'])
    assert any('lighting' not in item for item in result['created'])
    assert result['profile'].attributes == []
    assert any('没有可用画面帧' in notice for notice in result['notices'])


def test_a_frame_backed_bootstrap_writes_one_conservative_attribute(seeded):
    frame = np.full((48, 64, 3), 30, dtype=np.uint8)      # 暗画面
    with seeded.state.sessions() as db:
        result = bootstrap_module.bootstrap(db, 'rec', frame=frame)
        db.commit()
    attribute = result['profile'].attributes[0]
    assert attribute.key == 'lighting' and attribute.value['label'] == 'low_light'
    assert attribute.source_kind == 'frame'
    assert attribute.confidence == 0.5                     # 单帧不给高置信度
    assert attribute.hard_expiry_at is not None
    assert any('lighting=low_light' in item for item in result['created'])


def test_bootstrap_never_overwrites_what_is_already_there(seeded):
    from app.modules.semantics.schemas import IntrinsicInput
    with seeded.state.sessions() as db:
        semantics.update_intrinsic(db, 'cam', IntrinsicInput(values={'resolution': '自定义'}))
        db.commit()
    brighter = np.full((48, 64, 3), 240, dtype=np.uint8)
    with seeded.state.sessions() as db:
        first = bootstrap_module.bootstrap(db, 'cam', frame=brighter)
        db.commit()
        second = bootstrap_module.bootstrap(db, 'cam', frame=brighter)
        db.commit()
    assert first['profile'].intrinsic['resolution'] == '自定义'
    assert any('lighting' in item for item in first['created'])
    assert second['created'] == []
    assert any('已存在 lighting' in item for item in second['skipped'])


def test_the_bootstrap_endpoint_reports_the_profile_it_produced(seeded, client):
    response = client.post('/api/v1/sources/cam/semantic-profile/bootstrap')
    assert response.status_code == 200
    body = response.json()
    assert body['source_id'] == 'cam'
    assert body['profile']['intrinsic']['resolution'] == '960x540'
    assert any('摄像头源不做首帧取图' in notice for notice in body['notices'])
    unknown = client.post('/api/v1/sources/missing/semantic-profile/bootstrap')
    assert unknown.status_code == 404


class FakeDetector:
    """Deterministic stand-in so the comparison logic is testable offline."""

    def __init__(self, path, confidence=0.5):
        self.path = str(path)

    def detect(self, frame):
        value = int(frame[0, 0, 0])
        return [{'label': 'person', 'x': .1, 'y': .1, 'width': .2, 'height': .4,
                 'confidence': .9, 'marker': value}]


def frames(count=3):
    return [np.full((16, 16, 3), 10 * index, dtype=np.uint8) for index in range(count)]


def test_the_shadow_channel_is_deterministic_on_the_same_artifact():
    comparison = shadow.compare('model.onnx', 'model.onnx', frames(),
                                detector_factory=FakeDetector)
    assert comparison.available is True
    assert comparison.identical_artifact is True
    assert comparison.exact_frames == comparison.frames == 3
    assert comparison.agree is True
    assert comparison.detections_a == comparison.detections_b == 3
    assert any('确定性' in note for note in comparison.notes)


def test_a_missing_frame_batch_is_refused_instead_of_faked():
    comparison = shadow.compare('a.onnx', 'b.onnx', [], detector_factory=FakeDetector)
    assert comparison.available is False
    assert comparison.reason == '没有可供对照的帧'
    assert comparison.agree is False


def test_a_failing_detector_is_reported_as_unavailable():
    class Broken:
        def __init__(self, path, confidence=0.5):
            raise RuntimeError('会话无法创建')

    comparison = shadow.compare('a.onnx', 'b.onnx', frames(1), detector_factory=Broken)
    assert comparison.available is False
    assert '会话加载失败' in comparison.reason


def test_iou_matching_tolerates_small_geometry_differences():
    left = [{'x': .1, 'y': .1, 'width': .2, 'height': .4}]
    right = [{'x': .105, 'y': .1, 'width': .2, 'height': .4}]
    pairs, mean = shadow._match(left, right)
    assert len(pairs) == 1 and mean is not None and mean > 0.5
    far = [{'x': .8, 'y': .8, 'width': .1, 'height': .1}]
    assert shadow._match(left, far) == ([], None)
