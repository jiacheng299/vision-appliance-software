"""Algorithm-team port. Metadata/file imports never imply inference readiness.

An implementation must verify BOTH the inert file and all template declarations
against a trusted executor manifest/self-test. Never unpickle uploaded weights.
Deployment descriptors are server-owned and contain no secret endpoint addresses.
"""
import re
from ...shared.errors import Error
from .schemas import Deployment, ParseResult


class ModelServices:
    data_origin = 'real'

    def verify(self, definition, path, checksum):
        raise Error(503, 'model_verifier_unavailable', '算法校验适配器尚未接入；文件完整性检查不代表模型可执行。', retryable=True)

    def deployments(self):
        return []

    def parse(self, text, deployment):
        raise Error(503, 'analysis_service_unavailable', '本地需求解析服务尚未接入，可先手工填写条件并保存草稿。', retryable=True)

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
