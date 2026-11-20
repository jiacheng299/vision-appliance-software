"""LLM-assisted semantic profile analysis: sample consecutive frames and write dynamic attributes."""
import logging
from tempfile import TemporaryDirectory

from pathlib import Path

from ...shared.errors import Error
from ...shared.models import now
from ..settings import values_for
from .. import sources as sources_module
from .llm import ATTRIBUTE_KEYS, ProfileLlm
from .schemas import AttributeInput, IntrinsicInput
from . import service as semantics

FRAME_COUNT = 3
# Decay and hard expiry keep LLM output time-decayed like every other dynamic attribute.
TAU_SECONDS = 1800.0
HARD_EXPIRY_SECONDS = 7200.0


def default_frame_reader(config, db, source_id, gateway) -> list[bytes]:
    """Grab a few consecutive normal frames through the local decoder input."""
    from worker.media import LOCAL_INPUT, run_tool
    source, locator = sources_module.resolve_execution_input(db, config, source_id, gateway)
    with TemporaryDirectory(prefix='vision-profile-') as directory:
        target = str(Path(directory) / 'frame_%d.jpg')
        if source.kind == 'file':
            arguments = ['-nostdin', '-hide_banner', '-loglevel', 'error', '-y', *LOCAL_INPUT]
            if (source.duration_ms or 0) > 4000:
                arguments += ['-ss', '1']
            arguments += ['-i', locator, '-map', '0:v:0', '-frames:v', str(FRAME_COUNT),
                          '-q:v', '5', target]
        else:
            arguments = ['-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                         '-rtsp_transport', 'tcp', '-i', locator, '-map', '0:v:0',
                         '-frames:v', str(FRAME_COUNT), '-q:v', '5', target]
        try:
            run_tool(config.ffmpeg, arguments, min(config.media_timeout_seconds, 45))
        except Exception as failure:
            logging.getLogger(__name__).warning('Profile frame sampling failed: %s', failure)
            raise Error(422, 'profile_frames_unavailable',
                        '无法从视频源截取连续画面，请先确认视频源可正常预览。') from None
        frames = []
        for index in range(1, FRAME_COUNT + 1):
            path = Path(directory) / f'frame_{index}.jpg'
            if path.is_file():
                frames.append(path.read_bytes())
    if not frames:
        raise Error(422, 'profile_frames_unavailable', '未能从视频源截取到有效画面帧。')
    return frames


def analyze_profile(db, config, source_id, gateway=None, *, transport=None,
                    frame_reader=None) -> tuple:
    """Sample frames, ask the configured LLM, then write the profile attributes."""
    reader = frame_reader or default_frame_reader
    jpegs = reader(config, db, source_id, gateway)
    client = ProfileLlm(values_for(db, 'llm'), transport=transport)
    result = client.analyze_frames(jpegs)
    observed_at = semantics.epoch()
    written: list[str] = []
    for key in ATTRIBUTE_KEYS:
        item = result.get(key)
        if not item or not str(item.get('label') or '').strip():
            continue
        semantics.upsert_attribute(db, source_id, key, AttributeInput(
            value={'label': str(item['label']).strip()}, source_kind='probe',
            observed_at=observed_at, confidence=float(item.get('confidence') or 0.5),
            tau_seconds=TAU_SECONDS, hard_expiry_at=observed_at + HARD_EXPIRY_SECONDS))
        written.append(key)
    source = sources_module.get_source(db, source_id)
    if source.width and source.height:
        semantics.update_intrinsic(db, source_id, IntrinsicInput(
            values={'resolution': f'{source.width}x{source.height}'}))
    if not written:
        raise Error(422, 'llm_nothing_recognized',
                    '大模型没有从画面中确认任何动态属性，请换一段正常画面后重试。')
    return semantics.read_profile(db, source_id), written
