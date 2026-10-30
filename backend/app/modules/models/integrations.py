"""Algorithm-team port. Metadata/file imports never imply inference readiness.

An implementation must verify BOTH the inert file and all template declarations
against a trusted executor manifest/self-test. Never unpickle uploaded weights.
Deployment descriptors are server-owned and contain no secret endpoint addresses.
"""
import re
from ...shared.errors import Error
from .schemas import Deployment, ParseResult, TemplateMatch, MultimodalAnalysis


class ModelServices:
    data_origin = 'real'

    def verify(self, definition, path, checksum):
        raise Error(503, 'model_verifier_unavailable', '算法校验适配器尚未接入；文件完整性检查不代表模型可执行。', retryable=True)

    def deployments(self):
        return []

    def parse(self, text, deployment):
        raise Error(503, 'analysis_service_unavailable', '本地需求解析服务尚未接入，可先手工填写条件并保存草稿。', retryable=True)

    def match_template(self, text, catalog):
        raise Error(503, 'analysis_service_unavailable', '自然语言模板匹配服务尚未接入。', retryable=True)

    def analyze_multimodal(self, channel, sources, deployment):
        raise Error(503, 'multimodal_service_unavailable', '多模态任务分析与执行适配器尚未接入。', retryable=True)

    def analyze_frames(self, instruction, frames, deployment):
        raise Error(503, 'multimodal_service_unavailable', '多模态视频分析适配器尚未接入。', retryable=True)

    def evaluate(self, config, sources, catalog, deployment):
        raise Error(503, 'analysis_service_unavailable', '真实能力与证据评估服务尚未接入，不能确认可执行。', retryable=True)


class DemoModelServices(ModelServices):
    data_origin = 'mock'

    def verify(self, definition, path, checksum):
        return ('passed', '模拟校验通过：只用于演示目录和表单，不执行或加载该文件。')

    def deployments(self):
        return [Deployment(id='MOCK-local-parser', name='模拟本地解析器', version='1.0', usages=['requirement_parse'], inputs=['text'], location='本机模拟服务', health='healthy'),
                Deployment(id='MOCK-local-parser-2', name='模拟本地解析器（二）', version='2.0', usages=['requirement_parse'], inputs=['text'], location='本机模拟服务', health='healthy'),
                Deployment(id='MOCK-multimodal', name='模拟多模态模型', version='1.0', usages=['multimodal_analysis'], inputs=['text', 'image'], location='本机模拟服务', health='healthy')]

    def parse(self, text, deployment):
        target = 'person' if re.search(r'人|person', text, re.I) else 'vehicle' if re.search(r'车|vehicle', text, re.I) else None
        rule = 'dwell' if re.search(r'停留|滞留|逗留|dwell', text, re.I) else 'absence' if re.search(r'缺员|离岗|无人|absence', text, re.I) else 'intrusion' if re.search(r'进入|闯入|入侵|intrusion', text, re.I) else None
        duration = re.search(r'(\d+)\s*(秒|分钟|seconds?)', text, re.I)
        seconds = int(duration[1]) * (60 if duration[2] == '分钟' else 1) if duration else None
        missing = ([] if target else ['请明确监测目标。']) + ([] if rule else ['请明确受支持的触发规则；模拟解析仅识别进入、停留、缺员。'])
        if seconds is not None and not 0 < seconds <= 86400:
            seconds = None
        if rule in ('dwell', 'absence') and seconds is None:
            missing.append('请明确持续时长，不能自动将“太久”换算为秒数。')
        return ParseResult(target=target, rule=rule, duration_seconds=seconds, missing_conditions=missing,
            limitations=['关键词模拟解析，仅展示交互流程；请逐项核对，额外描述未被证明可执行。'],
            deployment_id=deployment.id if deployment else None, deployment_version=deployment.version if deployment else None, data_origin='mock')


    def match_template(self, text, catalog):
        # Deliberately narrow full-string mock grammar. Additional attributes,
        # conjunctions or negation are never silently discarded into a template.
        text = re.sub(r'[\s，。！？,!.?]', '', text)
        prefix = r'(?:请)?(?:检测|监测|识别)?(?:是否)?'
        suffix = r'(?:时|就)?(?:报警)?'
        patterns = [
            ('fire', 'presence', prefix + r'(?:有无|有)?(?:火源|火焰|着火)' + suffix),
            ('person', 'intrusion', prefix + r'(?:有)?(?:人员|人)(?:进入|闯入|入侵)(?:指定|这个)?区域(?:内)?' + suffix),
            ('person', 'dwell', prefix + r'(?:模拟)?(?:有)?(?:人员|人)(?:在)?(?:指定|这个)?区域(?:内)?(?:停留|滞留|逗留)(?:超过)?(?:(\d+)(秒|分钟))?(?:太久)?' + suffix),
            ('person', 'absence', prefix + r'(?:人员|人)(?:离岗|缺岗)(?:超过)?(?:(\d+)(秒|分钟))?' + suffix),
        ]
        for target, rule, pattern in patterns:
            match = re.fullmatch(pattern, text)
            if not match:
                continue
            item = next((i for i in catalog.items if target in i.targets and rule in i.rules), None)
            if not item:
                return None
            seconds = None
            if match.groups() and match[1]:
                seconds = int(match[1]) * (60 if match[2] == '分钟' else 1)
                if not 0 < seconds <= 86400:
                    return None
            return TemplateMatch(capability_ref=item.reference, target=target, rule=rule,
                duration_seconds=seconds, covers_all_requirements=True)
        return None

    def analyze_multimodal(self, channel, sources, deployment):
        text = channel.requirement_text
        duration = re.search(r'(\d+)\s*(秒|分钟)', text)
        seconds = int(duration[1]) * (60 if duration[2] == '分钟' else 1) if duration else channel.duration_seconds
        if seconds is not None and not 0 < seconds <= 86400:
            seconds = None
        requires_duration = bool(re.search(r'停留|滞留|持续|超过|太久|离岗', text))
        missing = []
        if re.search(r'异常|可疑|危险|不正常', text):
            missing.append('请用可观察的具体行为明确触发条件。')
        if requires_duration and seconds is None:
            missing.append('请明确持续时长。')
        return MultimodalAnalysis(target='visual_subject', rule='multimodal_observation', instruction=text,
            duration_seconds=seconds, requires_region='区域' in text, requires_duration=requires_duration,
            verdict='clarification_required' if missing else 'executable', missing_conditions=missing,
            limitations=['模拟多模态任务方案与运行，不调用真实视觉模型，也不能证明识别效果。'])
