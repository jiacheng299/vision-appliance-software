"""Run explicitly labelled local camera sources with MediaMTX and FFmpeg.

Recordings repeat; the university's public MJPEG camera remains a live input.
All local media and control listeners bind to 127.0.0.1 only.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
VAR = Path(os.environ.get('VISION_VAR_ROOT', ROOT / 'var'))
LAB = VAR / 'camera-lab'
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def verified_download(spec, target):
    def valid(path):
        return path.is_file() and path.stat().st_size == spec['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest() == spec['sha256']
    if valid(target):
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + '.part')
    try:
        print('Downloading ' + target.name, flush=True)
        with HTTP.open(spec['url'], timeout=60) as source, temporary.open('wb') as output:
            total = 0
            while block := source.read(256 * 1024):
                total += len(block)
                if total > spec['bytes']:
                    raise ValueError('Download exceeds expected size: ' + target.name)
                output.write(block)
        if not valid(temporary):
            raise ValueError('Download size or checksum mismatch: ' + target.name)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def prepare(spec):
    if os.name != 'nt':
        raise RuntimeError('This pinned camera lab installs Windows x64 tools.')
    archive = verified_download(spec['mediamtx'], LAB / 'downloads/mediamtx.zip')
    destination = LAB / 'tools'
    destination.mkdir(parents=True, exist_ok=True)
    # Extract only named files; never trust archive paths or execute installers.
    with zipfile.ZipFile(archive) as bundle:
        for name in ('mediamtx.exe', 'LICENSE'):
            content = bundle.read(name)
            installed = destination / name
            if not installed.is_file() or installed.read_bytes() != content:
                installed.write_bytes(content)
    for camera in spec['cameras']:
        if 'file' in camera:
            verified_download(camera, LAB / 'downloads' / camera['file'])
    ffmpeg = Path(os.environ.get('VISION_FFMPEG', VAR / 'tools/ffmpeg/bin/ffmpeg.exe'))
    if not ffmpeg.is_file():
        raise RuntimeError('FFmpeg is missing; run setup.cmd first.')
    return destination / 'mediamtx.exe', ffmpeg


def media_config(cameras):
    # Explicit paths keep unrelated publishers out of the local test server.
    lines = [
        'logLevel: info', 'rtsp: yes', 'rtspAddress: 127.0.0.1:8554',
        'rtspTransports: [tcp]', 'rtmp: no', 'srt: no', 'webrtc: no', 'moq: no',
        'hls: yes', 'hlsAddress: 127.0.0.1:8888', 'hlsAlwaysRemux: yes',
        'hlsVariant: fmp4', 'hlsSegmentDuration: 2s',
        'api: yes', 'apiAddress: 127.0.0.1:9997', 'paths:',
    ]
    for camera in cameras:
        name = camera['path']
        if not name.isascii() or not name.replace('_', '').isalnum():
            raise ValueError('Invalid camera path')
        lines.extend([f'  {name}:', '    source: publisher'])
    return '\n'.join(lines) + '\n'


def publisher_command(ffmpeg, camera, folder):
    command = [str(ffmpeg), '-hide_banner', '-loglevel', 'warning', '-nostdin']
    if 'file' in camera:
        command += ['-re', '-stream_loop', '-1', '-i', str(folder / camera['file'])]
    else:
        command += ['-rw_timeout', '15000000', '-reconnect', '1',
                    '-reconnect_streamed', '1', '-reconnect_delay_max', '3',
                    '-use_wallclock_as_timestamps', '1', '-i', camera['url']]
    # H.264/yuv420p and regular keyframes make the HLS output browser-friendly.
    command += ['-map', '0:v:0', '-an', '-vf', 'scale=960:-2,fps=15',
                '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
                '-pix_fmt', 'yuv420p', '-g', '30', '-keyint_min', '30',
                '-sc_threshold', '0', '-b:v', '1500k',
                '-f', 'rtsp', '-rtsp_transport', 'tcp',
                'rtsp://127.0.0.1:8554/' + camera['path']]
    return command


def request_api(path, method='GET', data=None):
    request = urllib.request.Request('http://127.0.0.1:8000/api/v1' + path,
        method=method, data=json.dumps(data).encode() if data is not None else None,
        headers={'Content-Type': 'application/json', 'Origin': 'http://127.0.0.1:8000'})
    with HTTP.open(request, timeout=10) as response:
        return json.load(response)


def register_sources(cameras, request=request_api):
    existing = []
    cursor = ''
    while True:
        page = request('/sources?kind=camera&limit=500' + ('&cursor=' + cursor if cursor else ''))
        existing.extend(page['items'])
        cursor = page.get('next_cursor')
        if not cursor:
            break
    result = []
    for camera in cameras:
        address = 'rtsp://127.0.0.1:8554/' + camera['path']
        source = next((s for s in existing if s['address'] == address), None)
        if source is None:
            source = request('/sources', 'POST', {'name': camera['name'], 'kind': 'camera', 'address': address})
        result.append({'id': source['id'], 'path': camera['path'], 'address': address})
    return result


def ensure_ports_free():
    for port in (8554, 8888, 9997):
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', port))
            except OSError as exc:
                raise RuntimeError(f'Port {port} is occupied; stop the previous camera lab first.') from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--register', action='store_true', help='Register sources through the running project API')
    parser.add_argument('--offline', action='store_true', help='Publish the two recordings without the public live camera')
    args = parser.parse_args()
    spec = json.loads((ROOT / 'deploy/camera-resources.json').read_text(encoding='utf8'))
    mediamtx, ffmpeg = prepare(spec)
    if args.prepare_only:
        return
    cameras = [c for c in spec['cameras'] if not args.offline or 'file' in c]
    ensure_ports_free()
    config = LAB / 'mediamtx.yml'
    config.write_text(media_config(cameras), encoding='utf8')
    logs = LAB / 'logs'
    logs.mkdir(exist_ok=True)
    children = []
    def launch(name, command):
        with (logs / (name + '.log')).open('a', encoding='utf8') as handle:
            process = subprocess.Popen(command, cwd=LAB, stdout=handle, stderr=subprocess.STDOUT)
        children.append(process)
        return process
    try:
        server = launch('mediamtx', [str(mediamtx), str(config)])
        deadline = time.monotonic() + 15
        while True:
            if server.poll() is not None:
                raise RuntimeError('MediaMTX exited; see var/camera-lab/logs/mediamtx.log')
            try:
                with socket.create_connection(('127.0.0.1', 8554), timeout=1):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    raise RuntimeError('MediaMTX startup timed out')
                time.sleep(.2)
        publishers = {c['path']: launch(c['path'], publisher_command(ffmpeg, c, LAB / 'downloads')) for c in cameras}
        if args.register:
            registrations = register_sources(cameras)
            (LAB / 'sources.json').write_text(json.dumps(registrations, indent=2), encoding='utf8')
        for camera in cameras:
            print(camera['name'] + '\n  rtsp://127.0.0.1:8554/' + camera['path'] +
                  '\n  http://127.0.0.1:8888/' + camera['path'] + '/', flush=True)
        print('Recordings are SIMULATED. Pendulum is a public LIVE camera. Ctrl+C stops this lab.', flush=True)
        retry_at = {}
        while server.poll() is None:
            children[:] = [p for p in children if p.poll() is None]
            for camera in cameras:
                name = camera['path']
                if publishers[name].poll() is not None and time.monotonic() >= retry_at.get(name, 0):
                    print('Publisher stopped; retrying ' + name + ' (see log)', flush=True)
                    publishers[name] = launch(name, publisher_command(ffmpeg, camera, LAB / 'downloads'))
                    retry_at[name] = time.monotonic() + 10
            time.sleep(1)
        raise RuntimeError('MediaMTX stopped; see its log')
    except KeyboardInterrupt:
        print('Stopping camera lab ...', flush=True)
    finally:
        for process in reversed(children):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as error:
        print('Camera lab failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
