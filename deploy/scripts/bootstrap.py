"""Install the framework into this checkout without global dependency changes."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def dependency_commands(python: Path, npm: str, root: Path = ROOT):
    """Locked application dependencies; the heavyweight exporter stays isolated."""
    return [
        ([python, '-m', 'pip', 'install', '-r', 'backend/requirements.txt'], root),
        ([python, '-m', 'pip', 'install', '-r', 'backend/requirements-vision.txt'], root),
        ([python, '-m', 'pip', 'check'], root),
        ([npm, 'ci'], root / 'frontend'),
        ([npm, 'run', 'build'], root / 'frontend'),
    ]


def install_component_archive(archive: Path, destination: Path, expected: str):
    with archive.open('rb') as file:
        if hashlib.file_digest(file, 'sha256').hexdigest() != expected:
            raise ValueError('Component checksum mismatch')
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        for item in entries:
            path = PurePosixPath(item.filename.replace('\\', '/'))
            if path.is_absolute() or '..' in path.parts or ':' in item.filename:
                raise ValueError('Unsafe component archive path')
        selected = {}
        for name in ('ffmpeg.exe', 'ffprobe.exe'):
            matches = [x for x in entries if PurePosixPath(x.filename).name == name]
            if len(matches) != 1:
                raise ValueError('Missing or ambiguous component: ' + name)
            selected[name] = matches[0]
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent, prefix='component-') as temp:
            staging = Path(temp)
            (staging / 'bin').mkdir()
            for name, item in selected.items():
                with bundle.open(item) as source, (staging / 'bin' / name).open('wb') as out:
                    shutil.copyfileobj(source, out)
            licenses = [x for x in entries if PurePosixPath(x.filename).name.upper().startswith(('LICENSE', 'COPYING')) and not x.is_dir()]
            for index, item in enumerate(licenses):
                (staging / f'LICENSE-{index}.txt').write_bytes(bundle.read(item))
            manifest = {'archive_sha256': expected, 'files': {}}
            for name in selected:
                manifest['files'][name] = hashlib.sha256((staging / 'bin' / name).read_bytes()).hexdigest()
            destination.mkdir(parents=True, exist_ok=True)
            (destination / 'bin').mkdir(exist_ok=True)
            for name in selected:
                os.replace(staging / 'bin' / name, destination / 'bin' / name)
            for item in staging.glob('LICENSE-*.txt'):
                shutil.copy2(item, destination / item.name)
            (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


def ensure_media_tools():
    if sys.platform != 'win32':
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            raise RuntimeError('Install ffmpeg and ffprobe locally before continuing.')
        return
    spec = json.loads((ROOT / 'deploy/components.json').read_text())['ffmpeg_windows_x64']
    dest = ROOT / 'var/tools/ffmpeg'
    manifest_file = dest / 'manifest.json'
    if manifest_file.is_file():
        manifest = json.loads(manifest_file.read_text())
        valid = manifest.get('archive_sha256') == spec['sha256']
        for name in ('ffmpeg.exe', 'ffprobe.exe'):
            path = dest / 'bin' / name
            valid = valid and path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == manifest.get('files', {}).get(name)
        if valid:
            print('Media tools already verified.', flush=True)
            return
    folder = ROOT / 'var/downloads'
    folder.mkdir(parents=True, exist_ok=True)
    archive = folder / ('ffmpeg-' + spec['version'] + '.zip')
    correct = archive.is_file() and hashlib.sha256(archive.read_bytes()).hexdigest() == spec['sha256']
    if not correct:
        temporary = archive.with_suffix('.download')
        try:
            print('Downloading pinned FFmpeg/FFprobe build ...', flush=True)
            with urllib.request.urlopen(spec['url'], timeout=60) as source, temporary.open('wb') as out:
                total = 0
                reported = 0
                while block := source.read(64 * 1024):
                    total += len(block)
                    if total > spec['bytes']:
                        raise ValueError('Component exceeds expected size')
                    out.write(block)
                    if total - reported >= 5 * 1024 * 1024:
                        print(f'Media tools: {total // (1024*1024)} / {spec["bytes"] // (1024*1024)} MiB', flush=True)
                        reported = total
                if total != spec['bytes']:
                    raise ValueError('Component download incomplete')
            with temporary.open('rb') as file:
                if hashlib.file_digest(file, 'sha256').hexdigest() != spec['sha256']:
                    raise ValueError('Downloaded component checksum mismatch')
            os.replace(temporary, archive)
        finally:
            temporary.unlink(missing_ok=True)
    install_component_archive(archive, dest, spec['sha256'])
    print('FFmpeg and FFprobe verified and installed.', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--components-only', action='store_true')
    parser.add_argument('--skip-components', action='store_true')
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 13):
        raise RuntimeError('Use Python 3.13 (64-bit) for this verified setup.')
    if not args.components_only:
        npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
        if not npm:
            raise RuntimeError('Install Node.js 22.12+ or 24 LTS, then reopen the terminal.')
        python = ROOT / ('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')
        if not python.exists():
            venv.EnvBuilder(with_pip=True).create(ROOT / '.venv')
        environment = dict(os.environ, PYTHONUTF8='1')
        for scheme, value in urllib.request.getproxies().items():
            if scheme in ('http', 'https'):
                environment.setdefault(scheme.upper() + '_PROXY', value)
        commands = dependency_commands(python, npm)
        for command, cwd in commands:
            subprocess.run(command, cwd=cwd, env=environment, check=True)
    if not args.skip_components:
        ensure_media_tools()
    print('Setup completed. Start with start.cmd; no model/API key is bundled.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'Setup failed: {error}', file=sys.stderr)
        raise SystemExit(1)
