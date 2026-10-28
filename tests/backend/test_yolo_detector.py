from pathlib import Path

import pytest

np = pytest.importorskip('numpy')
onnx = pytest.importorskip('onnx')
pytest.importorskip('onnxruntime')


def make_model(tmp_path, rows=(), input_shape=(1, 3, 640, 640), output_shape=None):
    from onnx import TensorProto, helper, numpy_helper
    values = np.zeros((1, 84, max(len(rows), 1)), dtype=np.float32)
    for index, (box, class_id, score) in enumerate(rows):
        values[0, :4, index] = box
        values[0, 4 + class_id, index] = score
    if output_shape is not None:
        values = np.zeros(output_shape, dtype=np.float32)
    graph = helper.make_graph(
        [helper.make_node('Constant', [], ['predictions'], value=numpy_helper.from_array(values))],
        'detector_fixture', [helper.make_tensor_value_info('images', TensorProto.FLOAT, input_shape)],
        [helper.make_tensor_value_info('predictions', TensorProto.FLOAT, list(values.shape))],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid('', 17)], ir_version=10)
    path = tmp_path / 'detector.onnx'
    onnx.save(model, path)
    return path


def detector(path, confidence=0.5):
    from app.modules.models.yolo import YoloPersonDetector
    return YoloPersonDetector(path, confidence=confidence)


def test_person_only_threshold_and_nms_with_real_onnx(tmp_path):
    path = make_model(tmp_path, [
        ((320, 320, 320, 320), 0, .9),
        ((322, 322, 320, 320), 0, .8),
        ((80, 80, 80, 80), 0, .49),
        ((80, 80, 80, 80), 1, .99),
    ])
    result = detector(path).detect(np.zeros((640, 640, 3), dtype=np.uint8))
    assert len(result) == 1
    assert result[0] == pytest.approx(dict(label='person', x=.25, y=.25, width=.5, height=.5, confidence=.9))


@pytest.mark.parametrize(('frame_shape', 'box', 'expected'), [
    ((100, 200, 3), (320, 320, 320, 160), (.25, .25, .5, .5)),
    ((200, 100, 3), (320, 320, 160, 320), (.25, .25, .5, .5)),
    ((100, 200, 3), (320, 320, 800, 800), (0, 0, 1, 1)),
    ((101, 200, 3), (320, 318, 320, 160), (.25, 25/101, .5, 50/101)),
])
def test_letterbox_reverse_coordinates_and_clip(tmp_path, frame_shape, box, expected):
    result = detector(make_model(tmp_path, [(box, 0, .9)])).detect(np.zeros(frame_shape, dtype=np.uint8))
    assert tuple(result[0][key] for key in ('x', 'y', 'width', 'height')) == pytest.approx(expected, abs=.002)


def test_preprocess_bgr_to_rgb_and_padding(tmp_path, monkeypatch):
    instance = detector(make_model(tmp_path))
    frame = np.full((100, 200, 3), (10, 20, 30), dtype=np.uint8)
    observed = []
    original = instance._session.run
    def capture(outputs, feeds):
        observed.append(next(iter(feeds.values())))
        return original(outputs, feeds)
    monkeypatch.setattr(instance._session, 'run', capture)
    assert instance.detect(frame) == []
    tensor = observed[0]
    assert tensor.shape == (1, 3, 640, 640)
    assert tensor[0, :, 320, 320] == pytest.approx([30/255, 20/255, 10/255])
    assert tensor[0, :, 0, 0] == pytest.approx([114/255]*3)


@pytest.mark.parametrize('frame', [np.empty((0, 10, 3), dtype=np.uint8), np.zeros((10, 10)), np.zeros((10, 10, 4), dtype=np.uint8), np.zeros((10, 10, 3), dtype=np.float32), None])
def test_invalid_frames_fail_explicitly(tmp_path, frame):
    with pytest.raises(ValueError, match='frame'):
        detector(make_model(tmp_path)).detect(frame)


@pytest.mark.parametrize('confidence', [-.1, 1.1, float('nan'), True])
def test_invalid_confidence_fails(tmp_path, confidence):
    with pytest.raises(ValueError, match='confidence'):
        detector(make_model(tmp_path), confidence)


@pytest.mark.parametrize('shape', [(1, 3, 0, 640), (1, 3, 'height', 640), (1, 4, 640, 640), (2, 3, 640, 640), (1, 3, 640, 99999)])
def test_invalid_model_input_dimensions_fail(tmp_path, shape):
    with pytest.raises(ValueError, match='input'):
        detector(make_model(tmp_path, input_shape=shape))


def test_invalid_model_output_fails(tmp_path):
    with pytest.raises(ValueError, match='output'):
        detector(make_model(tmp_path, output_shape=(1, 6, 100)))


def test_corrupt_or_missing_onnx_fails(tmp_path):
    path = tmp_path / 'bad.onnx'
    path.write_bytes(b'not an onnx')
    with pytest.raises(ValueError, match='ONNX'):
        detector(path)
    with pytest.raises(FileNotFoundError):
        detector(tmp_path / 'missing.onnx')


def test_nonfinite_model_predictions_fail_explicitly(tmp_path):
    path = make_model(tmp_path, [((float('nan'), 320, 100, 100), 0, .9)])
    with pytest.raises(ValueError, match='output'):
        detector(path).detect(np.zeros((640, 640, 3), dtype=np.uint8))


def test_nms_uses_unclipped_boxes_before_removing_letterbox_border(tmp_path):
    # Raw IoU is .25; clipping both to the visible image would falsely make IoU 1.
    path = make_model(tmp_path, [((320, 100, 320, 200), 0, .9), ((320, 175, 320, 50), 0, .8)])
    results = detector(path).detect(np.zeros((100, 200, 3), dtype=np.uint8))
    assert len(results) == 2
    assert all(result['y'] == 0 and result['height'] == pytest.approx(.125) for result in results)
