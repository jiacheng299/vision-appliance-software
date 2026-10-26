"""Composition adapters: B consumes A through its published capability port.

No B persistence is imported or written. Existing explicit provider injection
continues to work; default production runtime still fails closed.
"""
from ..agents.integrations import AgentServices
from ..agents.demo import DemoServices
from ..agents.contracts import Assessment
from . import service


class RegistryCapabilities:
    def init_registry(self, sessions, adapter):
        self.registry_sessions, self.model_adapter = sessions, adapter

    def catalog(self, actor_id):
        with self.registry_sessions() as db:
            value = service.catalog(db, self.data_origin)
        if self.data_origin == 'mock':
            builtin = DemoServices.catalog(self, actor_id)
            value.items = builtin.items + value.items
            value.fingerprint = service.digest([builtin.fingerprint, value.fingerprint])
        return value

    def assess(self, config, sources, actor_id):
        catalog = self.catalog(actor_id)
        if self.data_origin == 'real' and not catalog.items:
            self.unavailable('capability')
        result = service.deterministic_assessment(config, sources, catalog)
        if result.verdict != 'executable':
            return result
        if self.data_origin == 'mock':
            result.evidence_limitations = ['模拟能力/证据评估，不执行推理，也不保证原始自然语言中额外条件已被覆盖。']
            if self.scenario == 'insufficient_evidence':
                result.verdict = 'insufficient_evidence'
                result.evidence_limitations.append('模拟证据不足，不能启动。')
            return result
        with self.registry_sessions() as db:
            deployment = service.selected(db, self.model_adapter, 'multimodal_analysis')
        assessment = Assessment.model_validate(self.model_adapter.evaluate(config, sources, catalog, deployment))
        if assessment.data_origin != 'real' or assessment.capability_fingerprint != catalog.fingerprint:
            from ...shared.errors import Error
            raise Error(502, 'provider_contract_invalid', '评估来源或模型能力版本与当前目录不一致。')
        return assessment


class RegistryAgentServices(RegistryCapabilities, AgentServices):
    supports_grouped_sources = True


class RegistryDemoServices(RegistryCapabilities, DemoServices):
    pass
