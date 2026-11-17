"""模型能力表（M5）：能力不只记录类别，还记录观察前提、场景分桶质量与资源。

每一条能力都显式标注是否已标定。种子表里的质量数字是保守示例值，不是
实测准确率；没有分桶验证集的模型一律标记为未标定。
"""
from dataclasses import dataclass, field

DEFAULT_BUCKET = 'default'
BUCKETS = (DEFAULT_BUCKET, 'glare', 'low_light', 'snow', 'small_target', 'occluded')

# 画像属性取值 → 场景分桶。分桶决定读哪一列质量，缺省列必须单独给出。
LABEL_BUCKETS = {
    'strong_glare': 'glare', 'glare': 'glare', 'backlight': 'glare',
    'low_light': 'low_light', 'night': 'low_light', 'dim': 'low_light',
    'snow': 'snow', 'snowfall': 'snow',
}


@dataclass(frozen=True)
class Scenario:
    """求解时的观察条件快照，来自画像属性与实测画面指标。"""
    bucket: str = DEFAULT_BUCKET
    saturated_ratio: float | None = None
    target_px: float | None = None
    brightness: float | None = None
    blur: float | None = None
    reasons: tuple[str, ...] = ()

    @property
    def known(self):
        return self.bucket != DEFAULT_BUCKET or self.saturated_ratio is not None


@dataclass(frozen=True)
class Capability:
    id: str
    kind: str
    target: str
    label: str
    installed: bool
    calibrated: bool
    provides: tuple[str, ...]
    quality: dict = field(default_factory=dict)
    quality_by_bucket: dict = field(default_factory=dict)
    min_target_px: float | None = None
    brightness: tuple[float, float] | None = None
    max_blur: float | None = None
    max_overexposure: float | None = None
    min_fps: float | None = None
    repairs: dict = field(default_factory=dict)
    unrecoverable_saturation: float | None = None
    cpu_ms: float = 0.0
    memory_mb: float = 0.0
    shares_decoder: bool = False
    conflicts: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def quality_for(self, requirement_key, bucket=DEFAULT_BUCKET):
        column = self.quality_by_bucket.get(bucket) or {}
        if requirement_key in column:
            return float(column[requirement_key])
        return float(self.quality.get(requirement_key, 0.0))

    def bucket_supported(self, bucket):
        if bucket == DEFAULT_BUCKET:
            return True
        return bucket in self.quality_by_bucket or bucket in self.repairs.values()

    def repaired_bucket(self, scenario):
        """A preprocessor may convert the observed bucket into a workable one."""
        if not self.repairs or scenario.bucket not in self.repairs:
            return scenario.bucket
        if (scenario.saturated_ratio is not None and self.unrecoverable_saturation is not None
                and scenario.saturated_ratio > self.unrecoverable_saturation):
            # Saturated detail is gone: darkening the frame does not bring it back.
            return scenario.bucket
        return self.repairs[scenario.bucket]


# 种子能力表。真实安装的只有前三条；其余为"已声明未安装"，用于展示组合选择，
# 求解时会因未安装被判为不可行，而不是假装能跑。
SEED = (
    Capability(
        id='yolo11n-person', kind='detect', target='person',
        label='YOLO11n COCO 人员检测（CPU ONNX）',
        installed=True, calibrated=False,
        provides=('person_detect',),
        quality={'person_detect': 0.72},
        quality_by_bucket={'glare': {'person_detect': 0.45},
                           'low_light': {'person_detect': 0.55},
                           'snow': {'person_detect': 0.62},
                           'small_target': {'person_detect': 0.40},
                           'occluded': {'person_detect': 0.58}},
        min_target_px=24.0, brightness=(0.12, 0.92), max_blur=None,
        max_overexposure=0.20, min_fps=1.0,
        cpu_ms=48.0, memory_mb=420.0,
        limitations=('仅检测 person，不识别身份', '质量数字为保守示例值，未经分桶验证')),
    Capability(
        id='heuristic-tracker', kind='track', target='person',
        label='固定机位 IoU/中心距跟踪',
        installed=True, calibrated=True,
        provides=('person_track',), quality={'person_track': 0.65},
        cpu_ms=2.0, memory_mb=8.0,
        limitations=('不做身份识别', '依赖固定机位')),
    Capability(
        id='zone-rule', kind='event', target='person',
        label='监测区域相交与持续确认规则',
        installed=True, calibrated=True,
        provides=('zone_intersect',), quality={'zone_intersect': 0.90},
        cpu_ms=0.5, memory_mb=2.0),
    Capability(
        id='glare-removal', kind='preprocess', target='',
        label='去眩光预处理（未安装）',
        installed=False, calibrated=False,
        provides=(), quality={}, repairs={'glare': DEFAULT_BUCKET},
        unrecoverable_saturation=0.08, cpu_ms=12.0, memory_mb=64.0,
        limitations=('只能压缩可恢复的高光', '不可恢复饱和像素超过 8% 时无效')),
    Capability(
        id='center-crop', kind='preprocess', target='',
        label='中心区域裁剪放大（未安装）',
        installed=False, calibrated=False,
        provides=(), quality={}, repairs={'small_target': DEFAULT_BUCKET},
        cpu_ms=9.0, memory_mb=32.0,
        limitations=('以丢失周边视场为代价',)),
    Capability(
        id='yolo11s-person', kind='detect', target='person',
        label='YOLO11s 人员检测（未安装）',
        installed=False, calibrated=False,
        provides=('person_detect',),
        quality={'person_detect': 0.80},
        quality_by_bucket={'glare': {'person_detect': 0.52},
                           'low_light': {'person_detect': 0.63},
                           'snow': {'person_detect': 0.70},
                           'small_target': {'person_detect': 0.58}},
        min_target_px=18.0, brightness=(0.10, 0.94),
        max_overexposure=0.24, min_fps=1.0,
        cpu_ms=150.0, memory_mb=760.0,
        limitations=('质量数字为示例值，未经分桶验证',)),
)

TABLE = {capability.id: capability for capability in SEED}


def table():
    return TABLE


def get(capability_id):
    capability = TABLE.get(capability_id)
    if capability is None:
        raise KeyError(f'未知模型能力：{capability_id}')
    return capability


def bucket_for_labels(labels):
    """Semantic attribute labels → the scenario bucket used to read quality."""
    for label in labels:
        bucket = LABEL_BUCKETS.get(str(label).lower())
        if bucket:
            return bucket
    return DEFAULT_BUCKET


def scenario_from(*, labels=(), saturated_ratio=None, target_px=None,
                  brightness=None, blur=None):
    bucket = bucket_for_labels(labels)
    reasons = []
    if bucket != DEFAULT_BUCKET:
        reasons.append(f'场景分桶：{bucket}')
    return Scenario(bucket=bucket, saturated_ratio=saturated_ratio, target_px=target_px,
                    brightness=brightness, blur=blur, reasons=tuple(reasons))
