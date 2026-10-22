"""Integration tests for definitions; no model/camera service is needed."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

API = '/api/v1'


def create(admin, config=None, key=None, name='北门监测'):
    return admin.post(API+'/agents', json={'name': name, 'config': config or {'channels': []}}, headers={'Idempotency-Key': key or str(uuid4())})


def camera(admin):
    response = admin.post(API+'/sources', json={'kind': 'camera', 'name': '北门', 'address': 'rtsp://127.0.0.1/live'})
    assert response.status_code == 200
    return response.json()['id']


def test_agent_auth_csrf_and_viewer_cannot_write(client, admin, app):
    from app.shared.models import User
    from app.shared.security import password_hasher
    agent = create(admin).json()
    with TestClient(app) as anonymous:
        assert anonymous.get(API+'/agents').status_code == 401
    admin.headers.pop('X-CSRF-Token')
    assert create(admin).status_code == 403
    admin.headers['X-CSRF-Token'] = admin.cookies['vision_csrf']
    with app.state.sessions() as db:
        db.add(User(username='observer', role='viewer', password_hash=password_hasher.hash('observer-password')))
        db.commit()
    with TestClient(app) as viewer:
        viewer.post(API+'/auth/login', json={'username': 'observer', 'password': 'observer-password'})
        viewer.headers['X-CSRF-Token'] = viewer.cookies['vision_csrf']
        assert viewer.get(API+'/agents/'+agent['id']).status_code == 200
        assert create(viewer).status_code == 403
        assert viewer.patch(API+'/revisions/'+agent['latest_revision']['id'], json={'config': {'channels': []}, 'row_version': 1}).status_code == 403
        assert viewer.post(API+'/revisions/'+agent['latest_revision']['id']+'/validations').status_code == 403


def test_create_retry_is_idempotent_even_with_generated_channel_ids(admin):
    key = str(uuid4())
    config = {'channels': [{'name': '入口'}]}
    first, second = create(admin, config, key), create(admin, config, key)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert len(admin.get(API+'/agents').json()['items']) == 1
    conflict = create(admin, config, key, name='不同内容')
    assert conflict.status_code == 409
    assert conflict.json()['error']['code'] == 'idempotency_conflict'
    assert admin.post(API+'/agents', json={'name': '缺少幂等键'}).status_code == 422


def test_parallel_create_retry_produces_one_agent(admin, app):
    key = str(uuid4())
    cookies, csrf = dict(admin.cookies), admin.cookies['vision_csrf']
    def send(_):
        with TestClient(app, cookies=cookies, headers={'X-CSRF-Token': csrf}) as connection:
            return create(connection, key=key)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, range(2)))
    assert [r.status_code for r in results] == [201, 201]
    assert results[0].json()['id'] == results[1].json()['id']
    assert len(admin.get(API+'/agents').json()['items']) == 1


def test_clone_edit_does_not_change_base_and_stale_edit_conflicts(admin):
    agent = create(admin, {'channels': [{'name': '入口', 'duration_seconds': 30}]}).json()
    base = agent['latest_revision']
    command = {'base_revision_id': base['id'], 'row_version': agent['row_version']}
    key = str(uuid4())
    cloned = admin.post(API+f"/agents/{agent['id']}/revisions", json=command, headers={'Idempotency-Key': key})
    assert cloned.status_code == 201
    assert admin.post(API+f"/agents/{agent['id']}/revisions", json=command, headers={'Idempotency-Key': key}).json() == cloned.json()
    revision = cloned.json()
    assert revision['revision_no'] == 2 and revision['base_revision_id'] == base['id']
    revision['config']['channels'][0]['duration_seconds'] = 60
    body = {'config': revision['config'], 'row_version': revision['row_version']}
    assert admin.patch(API+'/revisions/'+revision['id'], json=body).status_code == 200
    conflict = admin.patch(API+'/revisions/'+revision['id'], json=body)
    assert conflict.status_code == 409
    assert admin.get(API+'/revisions/'+base['id']).json()['config']['channels'][0]['duration_seconds'] == 30
    detail = admin.get(API+'/agents/'+agent['id']).json()
    assert len(detail['revisions']) == 2
    assert detail['status'] == 'draft' and detail['execution_available'] is False
    assert admin.get(API+'/runs').json()['items'] == []


def test_parallel_draft_saves_have_one_winner(admin, app):
    revision = create(admin).json()['latest_revision']
    cookies, csrf = dict(admin.cookies), admin.cookies['vision_csrf']
    def save(name):
        with TestClient(app, cookies=cookies, headers={'X-CSRF-Token': csrf}) as connection:
            return connection.patch(API+'/revisions/'+revision['id'], json={'row_version': 1, 'config': {'channels': [{'name': name}]}})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ['编辑器 A', '编辑器 B']))
    assert sorted(r.status_code for r in results) == [200, 409]


def test_published_revision_is_immutable_and_can_be_cloned(admin, app):
    from app.modules.agents.models import AgentRevision
    agent = create(admin).json()
    rid = agent['latest_revision']['id']
    # Simulate a future publishing service, never provide a public publish bypass.
    with app.state.sessions() as db:
        db.get(AgentRevision, rid).state = 'published'
        db.commit()
    assert admin.patch(API+'/revisions/'+rid, json={'config': {'channels': []}, 'row_version': 1}).status_code == 409
    result = admin.post(API+f"/agents/{agent['id']}/revisions", json={'base_revision_id': rid, 'row_version': 1}, headers={'Idempotency-Key': str(uuid4())})
    assert result.status_code == 201 and result.json()['state'] == 'draft'


def test_invalid_references_and_archived_sources(admin):
    assert create(admin, {'channels': [{'name': '无效源', 'source_id': 'missing'}]}).status_code == 422
    sid = camera(admin)
    agent = create(admin, {'channels': [{'name': '入口', 'source_id': sid}]}).json()
    revision = agent['latest_revision']
    admin.post(API+'/sources/'+sid+'/archive')
    assert create(admin, {'channels': [{'name': '已归档', 'source_id': sid}]}).status_code == 422
    revision['config']['channels'][0]['requirement_text'] = '旧配置保留源引用，继续编辑说明'
    assert admin.patch(API+'/revisions/'+revision['id'], json={'config': revision['config'], 'row_version': 1}).status_code == 200
    other = create(admin).json()
    assert admin.post(API+f"/agents/{other['id']}/revisions", json={'base_revision_id': revision['id'], 'row_version': 1}, headers={'Idempotency-Key': str(uuid4())}).status_code == 422


@pytest.mark.parametrize('channel', [
    {'name': '非法时长', 'duration_seconds': -1},
    {'name': '布尔时长', 'duration_seconds': True},
    {'name': '区间不完整', 'start_media_ms': 0},
    {'name': '反向区间', 'start_media_ms': 1000, 'end_media_ms': 500},
    {'name': '越界坐标', 'regions': [{'id': 'r', 'points': [[0, 0], [2, 0], [0, 1]]}]},
    {'name': '共线区域', 'regions': [{'id': 'r', 'points': [[0, 0], [0.5, 0.5], [1, 1]]}]},
    {'name': '交叉区域', 'regions': [{'id': 'r', 'points': [[0, 0], [1, 1], [1, 0], [0, 1]]}]},
    {'name': '未知字段', 'trusted': True},
])
def test_invalid_config_does_not_create_partial_agent(admin, channel):
    assert create(admin, {'channels': [channel]}).status_code == 422
    assert admin.get(API+'/agents').json()['items'] == []


def test_file_interval_and_polygon_persist(admin, app):
    from app.shared.models import Source
    with app.state.sessions() as db:
        source = Source(name='录像', kind='file', status='ready', duration_ms=5000)
        db.add(source); db.commit(); sid = source.id
    channel = {'name': '录像通道', 'source_id': sid, 'start_media_ms': 0, 'end_media_ms': 5000, 'regions': [{'id': 'r', 'points': [[0.1, 0.1], [0.8, 0.1], [0.8, 0.8], [0.1, 0.8]]}]}
    saved = create(admin, {'channels': [channel]})
    assert saved.status_code == 201
    assert saved.json()['latest_revision']['config']['channels'][0]['regions'][0]['points'] == channel['regions'][0]['points']
    channel['end_media_ms'] = 5001
    assert create(admin, {'channels': [channel]}).status_code == 422
    channel['source_id'] = camera(admin)
    assert create(admin, {'channels': [channel]}).status_code == 422


def test_search_pagination_current_source_and_invalid_cursor(admin):
    sid = camera(admin)
    for name in ['北门 A', '北门 B', '南门']:
        assert create(admin, {'channels': [{'name': '通道', 'source_id': sid}]}, name=name).status_code == 201
    first = admin.get(API+'/agents', params={'q': '北门', 'limit': 1}).json()
    second = admin.get(API+'/agents', params={'q': '北门', 'limit': 1, 'cursor': first['next_cursor']}).json()
    assert first['next_cursor'] and second['next_cursor'] is None
    assert first['items'][0]['id'] != second['items'][0]['id']
    assert len(admin.get(API+'/agents', params={'source_id': sid}).json()['items']) == 3
    assert admin.get(API+'/agents', params={'cursor': '!!!'}).status_code == 422


def test_unavailable_evaluation_never_marks_draft_executable(admin):
    revision = create(admin).json()['latest_revision']
    result = admin.post(API+'/revisions/'+revision['id']+'/validations')
    assert result.status_code == 503
    assert result.json()['error']['code'] == 'capability_service_unavailable'
    assert admin.get(API+'/revisions/'+revision['id']).json() == revision


def test_agent_persists_after_app_restart_and_metadata_conflicts(admin, app):
    from app.main import create_app
    agent = create(admin).json()
    body = {'name': '新名称', 'description': '说明', 'row_version': 1}
    assert admin.patch(API+'/agents/'+agent['id'], json=body).status_code == 200
    assert admin.patch(API+'/agents/'+agent['id'], json=body).status_code == 409
    restarted = create_app(var_root=app.state.config.var_root, testing=True)
    with TestClient(restarted, cookies=dict(admin.cookies)) as connection:
        result = connection.get(API+'/agents/'+agent['id'])
        assert result.status_code == 200
        assert result.json()['name'] == '新名称'
        assert result.json()['latest_revision']['id'] == agent['latest_revision']['id']


def test_upgrade_from_foundation_keeps_existing_settings(tmp_path):
    from alembic import command
    from alembic.config import Config as AlembicConfig
    from pathlib import Path
    from sqlalchemy import text
    from app.shared.config import Config
    from app.shared.db import make_engine
    from app.main import create_app
    config = Config(var_root=tmp_path)
    config.prepare()
    engine = make_engine(config)
    migration = AlembicConfig()
    migration.set_main_option('script_location', str(Path(__file__).resolve().parents[2] / 'backend/alembic'))
    with engine.begin() as connection:
        migration.attributes['connection'] = connection
        command.upgrade(migration, '0001_foundation')
        connection.execute(text("INSERT INTO settings (section,\"values\",row_version) VALUES (:section,:value,1)"), {'section': 'general', 'value': '{"system_name":"existing installation"}'})
    engine.dispose()
    upgraded = create_app(var_root=tmp_path, testing=True)
    with upgraded.state.engine.connect() as connection:
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar() == '0003_agent_workflow'
        assert 'existing installation' in connection.execute(text('SELECT "values" FROM settings WHERE section=\'general\'')).scalar()
    upgraded.state.engine.dispose()
