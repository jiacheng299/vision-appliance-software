"""Trusted local YOLO11n verifier and model-resolution boundary."""
import importlib.util
import json
from pathlib import Path

from ...shared.config import ROOT
from ...shared.errors import Error
from ...shared.monitoring_parameters import ParameterSetting, validate_settings
from ..agents.schemas import CapabilityRef
from .integrations import ModelServices
from .multimodal_api import MultimodalApiClient
from .models import ModelFile, ModelPair
from .schemas import ModelInput
from .service import file_hash
from .yolo import YoloPersonDetector

SOURCE_SHA256 = '0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1'
COMMON_PARAMETERS = frozenset({'target', 'rule', 'duration_seconds', 'confidence_threshold', 'sample_interval_seconds'})
RULE_PARAMETERS = {
    'absence': COMMON_PARAMETERS | {'min_count', 'alarm_interval_seconds'},
    'intrusion': COMMON_PARAMETERS | {'tracking_timeout_seconds', 'exit_confirmation_seconds'},
}
RUNTIME_TYPE = 'yolo11n-onnx-person'


def dependencies_ready():
    try:
        for name in ('numpy', 'cv2', 'onnxruntime'):
            if importlib.util.find_spec(name) is None:
                return False
            importlib.import_module(name)
        return True
    except (ImportError, OSError, ValueError):
        return False


def black_frame():
    import numpy as np
    return np.zeros((640, 640, 3), dtype=np.uint8)


class YoloModelServices(ModelServices):
    def __init__(self, config, sessions):
        self.config, self.sessions = config, sessions
        self.multimodal_api = MultimodalApiClient(config)

    def deployments(self):
        deployment = self.multimodal_api.deployment()
        return [deployment] if deployment else []

    def analyze_multimodal(self, channel, sources, deployment):
        return self.multimodal_api.plan(channel, sources, deployment)

    def match_template(self, text, catalog):
        return self.multimodal_api.match_template(text, catalog)

    def analyze_frames(self, instruction, frames, deployment):
        return self.multimodal_api.analyze_frames(instruction, frames, deployment)

    def _artifact(self):
        root = self.config.var_root.resolve()
        folder = root / 'models/yolo11n'
        path = folder / 'yolo11n.onnx'
        manifest_path = folder / 'manifest.json'
        source = ROOT / 'deploy/yolo-model.json'
        if (not path.is_file() or not manifest_path.is_file() or manifest_path.stat().st_size > 65536
                or root not in path.resolve().parents or root not in manifest_path.resolve().parents):
            raise ValueError('Controlled artifact is unavailable')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        source_config = json.loads(source.read_text(encoding='utf-8'))
        if not isinstance(manifest, dict) or not isinstance(source_config, dict):
            raise ValueError('Invalid manifest structure')
        if (manifest.get('model') != 'yolo11n' or manifest.get('format') != 'onnx'
                or manifest.get('source_sha256') != SOURCE_SHA256
                or source_config.get('source_sha256') != SOURCE_SHA256
                or manifest.get('source_manifest_sha256') != file_hash(source)
                or manifest.get('model_version') != source_config.get('model_version')
                or manifest.get('source_url') != source_config.get('source_url')
                or manifest.get('export') != source_config.get('export')
                or manifest.get('input_shape') != [1, 3, 640, 640]
                or manifest.get('output_shape') != [1, 84, 8400]
                or Path(manifest.get('model_path', '')).resolve() != path.resolve()
                or manifest.get('sha256') != file_hash(path)):
            raise ValueError('Artifact provenance or integrity check failed')
        return manifest, path.resolve()

    def is_ready(self):
        try:
            self._artifact()
            return dependencies_ready()
        except (OSError, ValueError, TypeError, ImportError):
            return False

    def _definition_supported(self, definition, manifest):
        body = ModelInput.model_validate(definition)
        template = body.template
        rule = template.rules[0] if len(template.rules) == 1 else None
        if (body.runtime_type != RUNTIME_TYPE or body.version != manifest['model_version']
                or template.version != manifest['model_version']
                or template.targets != ['person'] or rule not in RULE_PARAMETERS
                or template.requires_region != [rule] or template.requires_duration != [rule]
                or not set(template.parameter_keys) <= RULE_PARAMETERS[rule]
                or not set(template.defaults) <= set(template.parameter_keys)):
            return False
        validate_settings([ParameterSetting(key=key, value=value) for key, value in template.defaults.items()],
                          extra_choices={'target': ['person'], 'rule': [rule]})
        return True

    def verify(self, definition, path, checksum):
        try:
            manifest, _ = self._artifact()
        except (OSError, ValueError, TypeError):
            raise Error(503, 'yolo_artifact_unavailable', '可信 YOLO11n 模型产物尚未就绪，请先运行模型准备脚本。') from None
        try:
            if (not self._definition_supported(definition, manifest) or checksum != manifest['sha256']
                    or not Path(path).is_file() or file_hash(Path(path)) != checksum):
                return 'failed', '模型文件或能力声明与可信 YOLO11n 人员监测执行清单不一致。'
        except (OSError, ValueError, TypeError, Error):
            return 'failed', '模型文件或能力声明不受当前 YOLO11n 执行器支持。'
        if not dependencies_ready():
            raise Error(503, 'yolo_dependencies_unavailable', '真实 YOLO 推理依赖尚未安装，不能认定模型可执行。')
        try:
            detector = YoloPersonDetector(Path(path), confidence=.5)
            detections = detector.detect(black_frame())
            if not isinstance(detections, list):
                raise ValueError('Invalid detector output')
        except Exception:
            return 'failed', '真实 YOLO11n ONNX 初始化或黑图推理自检失败。'
        return 'passed', '可信 YOLO11n 摘要、人员监测能力声明与真实 ONNX 黑图推理自检通过。'

    def resolve_model(self, reference: CapabilityRef) -> Path:
        try:
            reference = CapabilityRef.model_validate(reference)
            manifest, _ = self._artifact()
            if not dependencies_ready():
                raise ValueError('Dependencies unavailable')
            with self.sessions() as db:
                pair = db.get(ModelPair, (reference.model_id, reference.model_version))
                if (not pair or pair.validation != 'passed' or pair.status != 'available' or pair.data_origin != 'real'
                        or pair.template_id != reference.template_id or pair.template_version != reference.template_version
                        or not self._definition_supported(pair.definition, manifest)):
                    raise ValueError('Model reference is unavailable')
                file = db.get(ModelFile, pair.file_id)
                if not file or file.id != Path(file.id).name:
                    raise ValueError('Invalid file reference')
                controlled_root = self.config.var_root.resolve()
                root = (controlled_root / 'model-files').resolve()
                path = (root / file.id).resolve()
                if (controlled_root not in root.parents or root not in path.parents
                        or not path.is_file() or path.stat().st_size != file.size_bytes
                        or file.checksum != manifest['sha256'] or file_hash(path) != file.checksum):
                    raise ValueError('Model file has changed')
                return path
        except (OSError, ValueError, TypeError, Error):
            raise Error(422, 'yolo_model_unavailable', '模型引用、可信清单或本地文件校验失败，请重新校验模型后再启动。') from None
