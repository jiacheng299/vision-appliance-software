"""Integration ports, not alternate owners of Model/Run/Event/Media/Export data.

Install an implementation at the composition root (create_app(agent_services=...)).
The default fails closed. Each service can be independently unavailable.
The provider must enforce actor access, execution idempotency and atomic channel locks.
"""
from ...shared.errors import Error
from .contracts import (Assessment, CapabilityCatalog, ComparisonDTO, EventDetail, AgentEventPage,
                        ExportDTO, ExportDestinations, ExportInput, FeedbackInput, MissedDTO, MissedInput,
                        OperationDTO, PlaybackDTO, RunDTO, RuntimeCommand, ExecutionSummary)
from .schemas import RevisionConfig


class AgentServices:
    data_origin = 'real'
    supports_grouped_sources = False
    supports_multimodal_tasks = False
    supports_task_plans = False
    supports_configurable_parameters = False

    def deleting_task(self, agent_id, actor_id):
        self.unavailable('runtime')

    def available(self, service: str) -> bool:
        return False

    def unavailable(self, service):
        names = {'capability': '模型能力目录与需求评估', 'runtime': '监测运行', 'events': '报警与证据', 'media': '视频网关', 'exports': '报告导出'}
        code = 'capability_service_unavailable' if service == 'capability' else f'{service}_service_unavailable'
        raise Error(503, code, f'{names[service]}服务尚未接入或暂时不可用。已保存的数据不会因此删除。', retryable=True)

    def catalog(self, actor_id: str) -> CapabilityCatalog:
        self.unavailable('capability')

    def assess(self, config: RevisionConfig, sources: list[dict], actor_id: str) -> Assessment:
        self.unavailable('capability')

    def verify_execution_plans(self, config, actor_id):
        if any(c.execution_plan for c in config.channels):
            self.unavailable('capability')

    def summary(self, actor_id: str) -> ExecutionSummary:
        return ExecutionSummary(data_origin=self.data_origin)

    def runs(self, agent_id: str, actor_id: str) -> list[RunDTO]:
        self.unavailable('runtime')

    def submit(self, command: RuntimeCommand, actor_id: str, key: str) -> OperationDTO:
        self.unavailable('runtime')

    def operation(self, agent_id: str, operation_id: str, actor_id: str) -> OperationDTO:
        self.unavailable('runtime')

    def set_archived(self, agent_id: str, archived: bool, actor_id: str):
        """Atomically gate future starts and reject archiving active channels."""
        self.unavailable('runtime')

    def events(self, agent_id: str, actor_id: str, filters: dict, cursor: str | None = None, after: str | None = None) -> AgentEventPage:
        self.unavailable('events')

    def event(self, agent_id: str, event_id: str, actor_id: str) -> EventDetail:
        self.unavailable('events')

    def feedback(self, agent_id: str, event_id: str, body: FeedbackInput, actor_id: str, key: str) -> EventDetail:
        self.unavailable('events')

    def missed(self, agent_id: str, actor_id: str) -> list[MissedDTO]:
        self.unavailable('events')

    def add_missed(self, run: RunDTO, body: MissedInput, actor_id: str, key: str) -> MissedDTO:
        self.unavailable('events')

    def playback(self, run: RunDTO, actor_id: str) -> PlaybackDTO:
        self.unavailable('media')

    def detection_frame(self, run: RunDTO, actor_id: str):
        self.unavailable('media')

    def evidence(self, agent_id: str, event_id: str, evidence_id: str, actor_id: str) -> PlaybackDTO:
        self.unavailable('events')

    def release_playback(self, agent_id: str, session_id: str, actor_id: str):
        self.unavailable('media')

    def compare(self, baseline: RunDTO, candidate: RunDTO, actor_id: str) -> ComparisonDTO:
        self.unavailable('events')

    def export(self, agent_id: str, body: ExportInput, actor_id: str, key: str) -> ExportDTO:
        self.unavailable('exports')

    def export_destinations(self, actor_id: str) -> ExportDestinations:
        """Only public aliases; never return host paths to the browser."""
        self.unavailable('exports')

    def export_status(self, agent_id: str, export_id: str, actor_id: str) -> ExportDTO:
        self.unavailable('exports')

    def export_action(self, agent_id: str, export_id: str, action: str, actor_id: str, key: str) -> ExportDTO:
        self.unavailable('exports')

    def export_download(self, agent_id: str, export_id: str, actor_id: str) -> tuple[str, str, bytes]:
        self.unavailable('exports')
