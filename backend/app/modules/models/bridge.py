"""Composition adapters: B consumes A through its published capability port.

No B persistence is imported or written. Existing explicit provider injection
continues to work; default production runtime still fails closed.
"""
from ..agents.integrations import AgentServices
from ..agents.demo import DemoServices
from ..agents.contracts import Assessment, CapabilityItem
from ..agents.schemas import CapabilityRef
from ...shared.errors import Error
from . import service


class RegistryCapabilities:
    supports_multimodal_tasks = True
    supports_task_plans = True
    def init_registry(self, sessions, adapter):
        self.registry_sessions, self.model_adapter = sessions, adapter

    def catalog(self, actor_id):
        with self.registry_sessions() as db:
            value = service.catalog(db, self.data_origin)
        if self.data_origin == 'mock':
            builtin = DemoServices.catalog(self, actor_id)
            fire = CapabilityItem(name='模拟火源检测模型 + 火源模板', reference=CapabilityRef(model_id='MOCK-fire', model_version='1.0', template_id='MOCK-fire-template', template_version='1.0'), targets=['fire'], rules=['presence'], limitations=['模拟火源模板，仅供流程演示。'])
            value.items = builtin.items + [fire] + value.items
            value.fingerprint = service.digest([builtin.fingerprint, value.fingerprint])
        # Selection changes affect future planning, not existing plan snapshots.
        deployments = [[d.id, d.version, d.health, d.usages, d.inputs] for d in self.model_adapter.deployments()]
        value.fingerprint = service.digest([value.fingerprint, deployments])
        return value

    def verify_execution_plans(self, config, actor_id):
        from . import planning
        catalog = self.catalog(actor_id)
        with self.registry_sessions() as db:
            for c in config.channels:
                if c.task_mode == 'natural_language':
                    row = planning.verify(db, c, catalog, self.model_adapter)
                    if row.verdict != 'executable':
                        raise Error(422, 'execution_plan_blocked', '执行方案仍有未满足条件，不能启动。')

    def assess(self, config, sources, actor_id):
        catalog = self.catalog(actor_id)
        if self.data_origin == 'real' and not catalog.items and (not config.channels or any(c.task_mode != 'natural_language' for c in config.channels)):
            self.unavailable('capability')
        result = service.deterministic_assessment(config, sources, catalog)
        from . import planning
        with self.registry_sessions() as db:
            for c in config.channels:
                if c.task_mode == 'natural_language':
                    row = planning.verify(db, c, catalog, self.model_adapter)
                    if row.verdict != 'executable':
                        result.verdict = row.verdict
                        result.missing_conditions.extend(row.missing_conditions)
                    result.evidence_limitations.extend(row.limitations)
        if result.verdict != 'executable':
            return result
        if self.data_origin == 'mock':
            result.evidence_limitations.append('模拟能力/证据评估，不执行真实视觉推理。')
            if self.scenario == 'insufficient_evidence':
                result.verdict = 'insufficient_evidence'
                result.evidence_limitations.append('模拟证据不足，不能启动。')
            return result
        if all(c.task_mode in ('template', 'natural_language') for c in config.channels):
            return result
        with self.registry_sessions() as db:
            deployment = service.selected(db, self.model_adapter, 'multimodal_analysis')
        assessment = Assessment.model_validate(self.model_adapter.evaluate(config, sources, catalog, deployment))
        if assessment.data_origin != 'real' or assessment.capability_fingerprint != catalog.fingerprint:
            raise Error(502, 'provider_contract_invalid', '评估来源或模型能力版本与当前目录不一致。')
        return assessment


class RegistryAgentServices(RegistryCapabilities, AgentServices):
    supports_grouped_sources = True


class RegistryDemoServices(RegistryCapabilities, DemoServices):
    pass
