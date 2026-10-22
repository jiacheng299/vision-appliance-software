from unittest.mock import patch
import json
import pytest
from app.shared.models import Source, Job
from sqlalchemy import select
from worker.supervisor import Supervisor
from worker.media import MediaFailure
from worker.camera import decode_camera

API='/api/v1'

def test_decoder_requires_actual_frames(app):
    with patch('worker.camera.run_tool', return_value=json.dumps({'streams':[{'width':960,'height':540,'avg_frame_rate':'15/1','nb_read_frames':'0'}]}).encode()):
        with pytest.raises(MediaFailure) as caught:
            decode_camera(app.state.config,'plaza',5)
    assert caught.value.code=='camera_decode_failed'


def test_decoder_reads_frames_and_unknown_fps(app):
    with patch('worker.camera.run_tool', return_value=json.dumps({'streams':[{'width':960,'height':540,'avg_frame_rate':'0/0','nb_read_frames':'2'}]}).encode()):
        assert decode_camera(app.state.config,'plaza',5)=={'width':960,'height':540,'fps':None}


def test_periodic_checks_disconnect_recover_and_do_not_duplicate(client,app):
    source=client.post(API+'/sources',json={'name':'camera','kind':'camera','address':'rtsp://127.0.0.1:8554/plaza'}).json()
    worker=Supervisor(app.state.config)
    try:
        with app.state.sessions() as db:
            row=db.get(Source,source['id'])
            row.status='online'
            row.observed_at='2000-01-01T00:00:00Z'
            db.commit()
        assert worker.schedule_camera_check()
        assert not worker.schedule_camera_check()
        with patch('worker.supervisor.describe',side_effect=MediaFailure('camera_connection_failed','连接失败')):
            assert worker.run_once()
        assert client.get(API+'/sources/'+source['id']).json()['status']=='disconnected'
        assert not worker.schedule_camera_check()
        with app.state.sessions() as db:
            db.get(Source,source['id']).observed_at='2000-01-01T00:00:00Z'
            db.commit()
        with patch('worker.supervisor.describe'), patch('worker.supervisor.MediaGateway') as gateway, patch('worker.supervisor.decode_camera',return_value={'width':960,'height':540,'fps':15.0}):
            gateway.return_value.ensure_published.return_value='plaza'
            assert worker.run_once()
        result=client.get(API+'/sources/'+source['id']).json()
        assert result['status']=='online'
        assert result['error_code'] is None
        assert result['width']==960
        assert not worker.schedule_camera_check()
        client.post(API+'/sources/'+source['id']+'/archive')
        with app.state.sessions() as db:
            db.get(Source,source['id']).observed_at='2000-01-01T00:00:00Z'
            db.commit()
        assert not worker.schedule_camera_check()
    finally:
        worker.engine.dispose()
