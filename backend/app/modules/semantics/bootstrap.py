"""首次运行的画像初始化：只填该填的，绝不覆盖已有内容。

固有层来自设备记录（分辨率、设备标识、码流类型）；动态层只在能从一帧画面
真的测出亮度时写入一项 `lighting`，并把置信度压到保守值——一帧不足以支撑
"这是白天的常态"。所有写入都限定在缺项上，已有属性与固有字段保持不变。
"""
import time

from ...shared.models import now
from . import metrics as metrics_module
from . import service as semantics
from .models import ProfileAttribute, SemanticProfile
from .schemas import AttributeInput, IntrinsicInput

BRIGHT_LABEL = 'bright_light'
DARK_LABEL = 'low_light'
NEUTRAL_LABEL = 'daylight'
DARK_BELOW = 0.20
BRIGHT_ABOVE = 0.80
SINGLE_FRAME_CONFIDENCE = 0.5
LIGHTING_TAU_SECONDS = 300.0
LIGHTING_TTL_SECONDS = 1800.0


def sample_frame(path):
    """One frame from the first tenth of a recording, or None."""
    try:
        import cv2
    except ImportError:
        return None
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        return None
    try:
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total > 1:
            capture.set(cv2.CAP_PROP_POS_FRAMES, max(1, total // 10))
        ok, frame = capture.read()
        return frame if ok and frame is not None else None
    finally:
        capture.release()


def intrinsic_from(source):
    """Device record → intrinsic layer. Addresses and credentials never enter it."""
    values = {'device_id': source.id, 'stream': source.kind}
    if source.width and source.height:
        values['resolution'] = f'{source.width}x{source.height}'
    return values


def lighting_label(brightness):
    if brightness < DARK_BELOW:
        return DARK_LABEL
    if brightness > BRIGHT_ABOVE:
        return BRIGHT_LABEL
    return NEUTRAL_LABEL


def bootstrap(db, source_id, *, frame=None, at=None):
    """Fill missing intrinsic fields and, if a frame is given, one lighting attribute."""
    from .. import sources as sources_module
    source = sources_module.get_source(db, source_id)
    created, skipped, notices = [], [], []
    existing = semantics.read_profile(db, source_id, at)
    profile_row = semantics._profile(db, source_id, create=True)
    known = dict(profile_row.intrinsic or {})
    fill = {key: value for key, value in intrinsic_from(source).items() if not known.get(key)}
    if fill:
        semantics.update_intrinsic(db, source_id, IntrinsicInput(values=fill))
        created.extend(f'固有层 {key}={value}' for key, value in fill.items())
    else:
        skipped.append('固有层已完整')

    attributes = {row.key: row for row in db.query(ProfileAttribute)
                  .filter(ProfileAttribute.profile_id == profile_row.id).all()}
    if 'lighting' in attributes:
        skipped.append('已存在 lighting 属性，保持不动')
    elif frame is None:
        notices.append('没有可用画面帧，动态层保持为空：亮度类属性必须由实测画面写入。')
    else:
        measurement = metrics_module.measure_frame(frame)
        if measurement.brightness is None:
            notices.append('画面亮度未测定，动态层保持为空。')
        else:
            observed = time.time() if at is None else at
            label = lighting_label(measurement.brightness)
            semantics.upsert_attribute(db, source_id, 'lighting', AttributeInput(
                value={'label': label, 'brightness': round(measurement.brightness, 4)},
                source_kind='frame', observed_at=observed,
                confidence=SINGLE_FRAME_CONFIDENCE, tau_seconds=LIGHTING_TAU_SECONDS,
                hard_expiry_at=observed + LIGHTING_TTL_SECONDS))
            created.append(f'动态层 lighting={label}（单帧置信度 '
                           f'{SINGLE_FRAME_CONFIDENCE}，{int(LIGHTING_TTL_SECONDS)} 秒后失效）')
    return {'source_id': source_id, 'created': created, 'skipped': skipped,
            'notices': notices, 'profile': semantics.read_profile(db, source_id, at),
            'bootstrapped_at': now()}
