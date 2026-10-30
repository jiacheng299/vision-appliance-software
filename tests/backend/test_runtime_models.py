def register_model(app, *, identifier='runtime-person-model', file_id='runtime-model-file',
                   validation='passed', status='available', validation_message='模型校验通过。'):
    from app.modules.models.models import ModelFile, ModelPair

    definition = {
        'name': 'YOLO11n 人员检测',
        'version': '1.0.0',
        'runtime_type': 'yolo11n-onnx-person',
        'file_id': file_id,
        'template': {
            'name': '人员在岗监测',
            'version': '1.0.0',
            'targets': ['person'],
            'rules': ['absence'],
            'requires_region': ['absence'],
            'requires_duration': ['absence'],
        },
    }
    with app.state.sessions() as db:
        db.add(ModelFile(id=file_id, filename='yolo11n.onnx', size_bytes=10, checksum='a' * 64))
        db.add(ModelPair(model_id=identifier, version='1.0.0', template_id=f'{identifier}-template',
            template_version='1.0.0', file_id=file_id, definition=definition,
            validation=validation, validation_message=validation_message, status=status, data_origin='real'))
        db.commit()


def test_runtime_overview_lists_a_verified_model_when_the_executor_is_ready(client, app, monkeypatch):
    register_model(app)
    monkeypatch.setattr(app.state.model_services, 'is_ready', lambda: True)

    response = client.get('/api/v1/runtime/overview')

    assert response.status_code == 200, response.text
    assert response.json()['models'] == [{
        'id': 'runtime-person-model',
        'name': 'YOLO11n 人员检测',
        'version': '1.0.0',
        'runtime_type': 'yolo11n-onnx-person',
        'template_name': '人员在岗监测',
        'status': 'ready',
        'message': '模型校验通过，当前本地执行器可用。',
        'data_origin': 'real',
    }]


def test_runtime_overview_does_not_report_a_verified_model_ready_when_executor_is_down(client, app):
    register_model(app)

    model = client.get('/api/v1/runtime/overview').json()['models'][0]

    assert model['status'] == 'unavailable'
    assert model['message'] == '模型已校验，但本地执行器或可信模型产物当前不可用。'


def test_runtime_overview_preserves_pending_status_and_excludes_archived_versions(client, app):
    register_model(app, identifier='pending-model', file_id='pending-file', validation='pending',
                   validation_message='等待算法适配器校验。')
    register_model(app, identifier='archived-model', file_id='archived-file', status='archived')

    models = client.get('/api/v1/runtime/overview').json()['models']

    assert [(model['id'], model['status'], model['message']) for model in models] == [
        ('pending-model', 'pending', '等待算法适配器校验。'),
    ]
