"""Start application, worker and local video sources with python app.py."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
# Preserve backend imports for legacy commands run from the repository root.
__path__ = [str(ROOT / 'backend/app')]


def runtime_root(root):
    metadata = root / '.git'
    if metadata.is_file():
        target = metadata.read_text(encoding='utf8').strip().removeprefix('gitdir: ')
        return (root / target).resolve().parents[2]
    return root


def main():
    runtime = runtime_root(ROOT)
    python = runtime / ('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')
    if not python.is_file():
        raise RuntimeError('Virtual environment missing. Run setup.cmd first.')
    # Keep the root app.py from shadowing the backend's app package.
    environment = dict(os.environ, PYTHONUTF8='1', PYTHONSAFEPATH='1')
    environment.setdefault('VISION_VAR_ROOT', str(runtime / 'var'))
    environment['VISION_FRONTEND_DIST'] = str(ROOT / 'frontend/dist')
    for name in ('ffmpeg', 'ffprobe'):
        suffix = '.exe' if os.name == 'nt' else ''
        environment.setdefault('VISION_' + name.upper(), str(runtime / 'var/tools/ffmpeg/bin' / (name + suffix)))
    children = []
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    def launch(script, *arguments):
        process = subprocess.Popen([str(python), '-u', script, *arguments], cwd=ROOT,
                                   env=environment, creationflags=flags)
        children.append(process)
        return process
    try:
        api = launch('deploy/scripts/run.py')
        http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 90
        while True:
            if api.poll() is not None:
                raise RuntimeError('Application stopped during startup. See var/logs/api.log.')
            try:
                with http.open('http://127.0.0.1:8000/', timeout=1):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Application startup timed out.')
                time.sleep(.5)
        cameras = launch('deploy/scripts/simulated_cameras.py', '--register')
        print('Application: http://127.0.0.1:8000 | Ctrl+C stops all services.', flush=True)
        while api.poll() is None and cameras.poll() is None:
            time.sleep(.5)
        raise RuntimeError('A service stopped. See startup output and var/camera-lab/logs.')
    except KeyboardInterrupt:
        print('\nStopping all services ...', flush=True)
    finally:
        for process in reversed(children):
            if process.poll() is None:
                try:
                    if os.name == 'nt':
                        process.send_signal(signal.CTRL_BREAK_EVENT)
                    else:
                        process.terminate()
                    process.wait(timeout=15)
                except (OSError, subprocess.TimeoutExpired):
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                    else:
                        process.kill()


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError) as error:
        print('Start failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
