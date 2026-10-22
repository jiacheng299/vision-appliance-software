import httpx
import pytest
from unittest.mock import patch
from app.shared.media_gateway import MediaGateway

API = '/api/v1'


def camera(client, address='rtsp://127.0.0.1:8554/plaza'):
    response = client.post(API+'/sources', json={'name':'模拟广场', 'kind':'camera', 'address':address})
    assert response.status_code == 200
    return response.json()


def attach(app, handler):
    app.state.media_gateway.close()
    app.state.media_gateway = MediaGateway(app.state.config, transport=httpx.MockTransport(handler))


def test_camera_preview_returns_same_origin_hls_without_credentials(client, app):
    source = camera(client)
    attach(app, lambda r: httpx.Response(200, json={'name':'plaza', 'ready':True, 'tracks':['H264'], 'items':[]}))
    response = client.post(f"{API}/sources/{source['id']}/preview-sessions")
    assert response.status_code == 200, response.text
    assert response.json()['protocol'] == 'hls'
    assert response.json()['playback_url'] == f"{API}/sources/{source['id']}/live/index.m3u8"
    assert client.get(API+'/health/ready').json()['services'][3]['status'] == 'ready'


def test_hls_manifests_and_segments_stay_under_source_route(client, app):
    source = camera(client)
    def handler(request):
        if request.url.port == 9997:
            return httpx.Response(200, json={'name':'plaza','ready':True})
        if request.url.path.endswith('.m3u8'):
            return httpx.Response(200, text='#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\nsegment1.m4s\n')
        return httpx.Response(200, content=b'video-segment', headers={'Content-Type':'video/mp4'})
    attach(app, handler)
    root = f"{API}/sources/{source['id']}/live/"
    response = client.get(root+'index.m3u8')
    assert response.status_code == 200, response.text
    assert f'URI="{root}init.mp4"' in response.text
    assert root+'segment1.m4s' in response.text
    assert client.get(root+'segment1.m4s').content == b'video-segment'
    assert client.post(API+'/sources/'+source['id']+'/archive').status_code == 204
    assert client.get(root+'segment1.m4s').status_code == 404


def test_missing_gateway_stays_unavailable_and_never_sets_online(client, app):
    source = camera(client)
    attach(app, lambda r: httpx.Response(503))
    response = client.post(f"{API}/sources/{source['id']}/preview-sessions")
    assert response.status_code == 503
    assert client.get(API+'/sources/'+source['id']).json()['status'] != 'online'


def test_unpublished_external_camera_does_not_trigger_outbound_rtsp(client, app):
    source = camera(client, 'rtsp://127.0.0.1:554/private')
    calls = []
    attach(app, lambda r: calls.append(str(r.url)) or httpx.Response(200, json={'ready':True}))
    assert client.post(f"{API}/sources/{source['id']}/preview-sessions").status_code == 503
    assert not calls


@pytest.mark.parametrize('reference', ['https://external.example/secret', '../secret.mp4', '%2e%2e/secret.mp4'])
def test_manifest_cannot_escape_gateway_source(client, app, reference):
    source = camera(client)
    attach(app, lambda r: httpx.Response(200, json={'ready':True}) if r.url.port == 9997
           else httpx.Response(200, text='#EXTM3U\n'+reference+'\n'))
    response = client.get(f"{API}/sources/{source['id']}/live/index.m3u8")
    assert response.status_code == 502
    assert 'external.example' not in response.text


def test_gateway_redirect_cannot_contact_other_origin(client, app):
    source = camera(client)
    calls = []
    def handler(request):
        calls.append(str(request.url))
        if request.url.port == 9997:
            return httpx.Response(200, json={'ready':True})
        return httpx.Response(302, headers={'Location':'http://external.example/secret'})
    attach(app, handler)
    assert client.get(f"{API}/sources/{source['id']}/live/index.m3u8").status_code == 502
    assert all('external.example' not in url for url in calls)


def test_camera_connection_test_recognizes_published_gateway_stream(client, app):
    from worker.supervisor import Supervisor
    source = camera(client)
    job = client.post(f"{API}/sources/{source['id']}/tests").json()
    with patch('worker.supervisor.describe'), patch('worker.supervisor.decode_camera', return_value={'width':960,'height':540,'fps':15.0}, create=True), patch('worker.supervisor.MediaGateway') as gateway:
        gateway.return_value.ensure_published.return_value = 'plaza'
        worker = Supervisor(app.state.config)
        try:
            assert worker.run_once()
        finally:
            worker.engine.dispose()
    result = client.get(f"{API}/sources/{source['id']}").json()
    assert result['status'] == 'online'
    assert (result['width'], result['height'], result['fps']) == (960,540,15.0)
    assert result['error_code'] is None
    report = client.get(API+'/source-tests/'+job['id']).json()
    assert report['state'] == 'completed'
    assert '解码' in report['message']
