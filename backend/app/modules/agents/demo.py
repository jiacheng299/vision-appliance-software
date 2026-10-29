"""Explicit, isolated in-memory test doubles. No model/video/production results.

This file owns only synthetic data. Production uses AgentServices and never instantiates it.
State transitions are timer-driven on reads so no inference worker is impersonated.
"""
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
import json
import base64
from threading import RLock
import time
from uuid import uuid4, uuid5, NAMESPACE_URL
from zoneinfo import ZoneInfo
from ...shared.errors import Error
from ...shared.models import now
from .contracts import *
from .integrations import AgentServices
from .schemas import channel_sources
from .workflow import digest


def identifier():
    return str(uuid4())


class DemoServices(AgentServices):
    data_origin = 'mock'
    supports_grouped_sources = True
    supports_configurable_parameters = True

    def __init__(self):
        self.lock = RLock(); self.scenario = 'normal'; self.offset = 0
        self.run_rows = {}; self.operations = {}; self.commands = {}; self.started = {}; self.busy = {}
        self.event_rows = {}; self.annotations = {}; self.changes = []; self.sequence = 0
        self.receipts = {}; self.jobs = {}; self.job_payloads = {}; self.job_started = {}; self.sessions = {}; self.archived = set()
        self.fingerprint = 'MOCK-person-registry-1.0'

    def clock(self):
        return time.monotonic()+self.offset

    @contextmanager
    def deleting_task(self,agent_id,actor_id):
        with self.lock:
            yield lambda db:None
            run_ids={key for key,value in self.run_rows.items() if value.agent_id==agent_id}
            for rows in (self.run_rows,self.operations,self.event_rows,self.annotations,self.jobs,self.sessions):
                for key,value in list(rows.items()):
                    if getattr(value,'agent_id',None)==agent_id or getattr(value,'run_id',None) in run_ids:
                        rows.pop(key,None)
            for key,(_,value) in list(self.receipts.items()):
                if getattr(value,'agent_id',None)==agent_id:self.receipts.pop(key,None)
            self.archived.add(agent_id)

    def advance(self, seconds=5):
        with self.lock:
            self.offset += seconds; self.tick()

    def available(self, service):
        return not ((service == 'capability' and self.scenario == 'model_unavailable') or (service == 'media' and self.scenario == 'video_disconnected') or (service == 'events' and self.scenario == 'events_disconnected'))

    def check(self, name):
        if not self.available(name):
            self.unavailable(name)

    def catalog(self, actor_id):
        self.check('capability')
        from ...shared.monitoring_parameters import BY_KEY
        return CapabilityCatalog(items=[CapabilityItem(name='模拟人员模型 + 模拟区域模板',
            reference=CapabilityRef(model_id='MOCK-person', model_version='1.0', template_id='MOCK-region', template_version='1.0'),
            targets=['person'], rules=['intrusion', 'dwell', 'absence'], requires_region=['intrusion', 'dwell', 'absence'],
            requires_duration=['dwell', 'absence'], parameter_keys=list(BY_KEY),limitations=['仅用于演示接口交互，不执行人员识别，也不能证明任何场景效果。'])], fingerprint=self.fingerprint, data_origin='mock')

    def assess(self, config, sources, actor_id):
        catalog = self.catalog(actor_id); item = catalog.items[0]
        missing, unsupported = [], []
        for c in config.channels:
            if c.capability_ref != item.reference:
                unsupported.append(f'{c.name}：请选择模拟能力目录中的有效模型与模板。')
            if c.target not in item.targets:
                unsupported.append(f'{c.name}：模拟模型只声明支持 person，未覆盖 {c.target or "未指定目标"}。')
            if c.rule not in item.rules:
                unsupported.append(f'{c.name}：模拟模板未声明支持规则 {c.rule or "未指定规则"}。')
            for binding in channel_sources(c):
                if c.rule in item.requires_region and not binding.regions:
                    missing.append(f'{c.name} / {binding.source_id}：请为这个视频源绘制监测区域。')
            if c.rule in item.requires_duration and not c.duration_seconds:
                missing.append(f'{c.name}：请明确持续时长。')
        verdict = 'unsupported' if unsupported else 'clarification_required' if missing else 'insufficient_evidence' if self.scenario == 'insufficient_evidence' else 'executable'
        return Assessment(verdict=verdict, missing_conditions=missing, unsupported_conditions=unsupported,
            evidence_limitations=['模拟结果不代表真实模型效果。']+(['模拟证据条件不足，不能确认发布。'] if verdict == 'insufficient_evidence' else []),
            capability_fingerprint=self.fingerprint, chosen_capabilities=[item.reference], data_origin='mock')

    def replay(self, actor, key, action, body):
        token = (actor, key); hashed = digest([action, body])
        if token in self.receipts:
            original, result = self.receipts[token]
            if original != hashed:
                raise Error(409, 'idempotency_conflict', '同一请求编号已用于不同内容。')
            return result.model_copy(deep=True), hashed
        return None, hashed

    def remember(self, actor, key, hashed, result):
        self.receipts[(actor, key)] = (hashed, result.model_copy(deep=True))
        return result.model_copy(deep=True)

    def summary(self, actor_id):
        with self.lock:
            self.tick()
            result = ExecutionSummary(data_origin='mock')
            if self.available('runtime'):
                rows = list(self.run_rows.values())
                result.active_runs = sum(r.state in ACTIVE_STATES for r in rows)
                result.waiting = sum(r.state == 'queued' for r in rows)
                result.running = result.active_runs - result.waiting
                result.completed = sum(r.state == 'completed' for r in rows)
                result.failed = sum(r.state == 'failed' for r in rows)
            if self.available('events'):
                zone = ZoneInfo('Asia/Shanghai')
                today = datetime.now(zone).date()
                rows = list(self.event_rows.values())
                result.today_events = sum(datetime.fromisoformat(e.occurred_at.replace('Z', '+00:00')).astimezone(zone).date() == today for e in rows)
                result.recent_events = [AgentEventDTO.model_validate(e.model_dump(exclude={'evidence', 'feedback_history'}))
                    for e in sorted(rows, key=lambda e: (e.occurred_at, e.id), reverse=True)[:50]]
            return result

    def runs(self, agent_id, actor_id):
        with self.lock:
            self.tick()
            return [r.model_copy(deep=True) for r in sorted(self.run_rows.values(), key=lambda r: r.created_at or r.started_at or '', reverse=True) if r.agent_id == agent_id]

    def set_archived(self, agent_id, archived, actor_id):
        with self.lock:
            self.tick()
            if archived and (any(owner == agent_id for owner, _ in self.busy) or any(r.agent_id == agent_id and r.state in ACTIVE_STATES for r in self.run_rows.values())):
                raise Error(409, 'agent_in_use', '请先停止所有运行和排队通道，再归档。')
            if archived:
                self.archived.add(agent_id)
            else:
                self.archived.discard(agent_id)

    def submit(self, command, actor_id, key):
        with self.lock:
            self.tick()
            replay, hashed = self.replay(actor_id, key, 'run-command', command.model_dump(mode='json'))
            if replay:
                # Return current authoritative operation, not its initial pending copy.
                return self.operations[replay.id].model_copy(deep=True)
            if command.agent_id in self.archived and command.kind != 'stop':
                raise Error(409, 'agent_archived', '智能体已经归档。')
            active = [r for r in self.run_rows.values() if r.agent_id == command.agent_id and r.channel_id in command.channel_ids and r.state in ACTIVE_STATES]
            if command.kind == 'stop' and command.stop_channel_id:
                scope = [command.stop_channel_id]
                if set(r.id for r in active) != set(command.expected_active_run_ids):
                    raise Error(409, 'run_scope_changed', '通道运行已变化，请刷新。')
                pairs = [(r.channel_id, r.source_id) for r in active]
            elif command.kind == 'stop':
                target = self.run_rows.get(command.stop_run_id)
                if not target or target.agent_id != command.agent_id:
                    raise Error(404, 'run_not_found', '运行不存在。')
                active = [target] if target.state in ACTIVE_STATES else []
                scope = [target.channel_id]; pairs = [(target.channel_id, target.source_id)]
            else:
                scope = command.channel_ids
                if set(r.id for r in active) != set(command.expected_active_run_ids):
                    raise Error(409, 'run_scope_changed', '实际运行已发生变化，请刷新后核对。')
                if active and command.kind == 'start':
                    raise Error(409, 'channel_busy', '所选通道正在运行，请使用应用配置或先停止。')
                pairs = [(c.channel_id, b.source_id) for c in command.config.channels if c.channel_id in scope for b in channel_sources(c)]
                pairs += [(r.channel_id, r.source_id) for r in active]
                pairs = list(dict.fromkeys(pairs))
            if not pairs:
                raise Error(422, 'invalid_channel_scope', '所选通道没有可执行的视频源。')
            if any((command.agent_id, c) in self.busy for c in scope):
                raise Error(409, 'channel_busy', '通道正在执行另一项操作，请等待结果。')
            op = OperationDTO(id=identifier(), agent_id=command.agent_id, kind=command.kind, state='pending',
                channels=[ChannelOperation(channel_id=c, source_id=sid, state='pending', old_run_id=next((r.id for r in active if r.channel_id == c and r.source_id == sid), None)) for c,sid in pairs], message='模拟操作已受理，按通道处理，各视频独立记录结果。', data_origin='mock')
            self.operations[op.id] = op; self.commands[op.id] = command.model_copy(deep=True); self.started[op.id] = self.clock()
            for c in scope:
                self.busy[(command.agent_id, c)] = op.id
            return self.remember(actor_id, key, hashed, op)

    def operation(self, agent_id, operation_id, actor_id):
        with self.lock:
            self.tick()
            op = self.operations.get(operation_id)
            if not op or op.agent_id != agent_id:
                raise Error(404, 'operation_not_found', '操作不存在。')
            return op.model_copy(deep=True)

    def tick(self):
        for op in self.operations.values():
            if op.state not in ('pending', 'running'):
                continue
            elapsed = self.clock()-self.started[op.id]; command = self.commands[op.id]
            if elapsed < .25:
                continue
            op.state = 'running'
            for index, item in enumerate(op.channels):
                if item.state in ('succeeded', 'failed', 'canceled'):
                    continue
                if item.old_run_id and elapsed < .8:
                    item.state = 'stopping_old'
                    old = self.run_rows[item.old_run_id]
                    if old.state in ACTIVE_STATES:
                        old.state = 'stopping'
                    continue
                if item.old_run_id:
                    old = self.run_rows[item.old_run_id]
                    if self.scenario == 'stop_failed' and index == 0:
                        old.state = 'running'; old.last_heartbeat_at = now()
                        item.state = 'failed'; item.message = '模拟停止失败，旧运行仍在运行，未启动新版本。'
                        continue
                    if old.state in ACTIVE_STATES:
                        old.state = 'stopped'; old.ended_at = now(); old.message = '由用户控制停止（模拟）。'
                if command.kind == 'stop':
                    item.state = 'succeeded'; item.message = '模拟运行已停止。'; continue
                item.state = 'starting_new'
                if elapsed < 1.3:
                    continue
                channel = next(c for c in command.config.channels if c.channel_id == item.channel_id)
                binding = next((b for b in channel_sources(channel) if b.source_id == item.source_id), None)
                if binding is None:
                    item.state = 'succeeded'; item.message = '此视频源已从新配置移除，旧运行已停止。'; continue
                failed = self.scenario == 'start_failed' and index == 0
                queued = self.scenario == 'resource_queued' and not failed
                run = RunDTO(id=identifier(), agent_id=op.agent_id, revision_id=command.revision_id,
                    revision_no=command.revision_no, channel_id=channel.channel_id, channel_name=channel.name,
                    source_id=binding.source_id, source_kind=command.source_kinds[binding.source_id],
                    created_at=now(), recording_available=command.source_kinds[binding.source_id] == 'file',
                    source_snapshot=next((s for s in command.source_snapshots if s.id == binding.source_id), None),
                    state='failed' if failed else 'queued' if queued else 'running', config_snapshot=command.config.model_copy(deep=True),
                    started_at=None if queued else now(), ended_at=now() if failed else None,
                    last_heartbeat_at=None if queued or failed else now(), start_media_ms=binding.start_media_ms, end_media_ms=binding.end_media_ms,
                    processed_media_ms=0 if command.source_kinds[binding.source_id] == 'file' else None,
                    selected_duration_ms=(binding.end_media_ms-binding.start_media_ms) if binding.end_media_ms is not None else 60000 if command.source_kinds[binding.source_id] == 'file' else None,
                    message='模拟启动失败；旧运行若已停止，不会自动恢复。' if failed else '模拟资源不足，已排队，尚未运行。' if queued else '模拟运行中，不执行真实识别。',
                    error_code='MOCK_START_FAILED' if failed else None, baseline_run_id=command.baseline_run_id, data_origin='mock')
                self.run_rows[run.id] = run; item.new_run_id = run.id
                item.state = 'failed' if failed else 'succeeded'; item.message = run.message
                if not failed and not queued:
                    self.add_event(run)
            if all(c.state in ('succeeded', 'failed', 'canceled') for c in op.channels):
                failed = sum(c.state == 'failed' for c in op.channels)
                op.state = 'failed' if failed == len(op.channels) else 'partial_failed' if failed else 'succeeded'
                op.message = '模拟操作结束，请按每一路实际运行状态核对结果。'
                for c in op.channels:
                    self.busy.pop((op.agent_id, c.channel_id), None)
        for run in self.run_rows.values():
            if run.state == 'queued' and self.scenario != 'resource_queued':
                run.state = 'running'; run.started_at = now(); run.message = '模拟资源恢复，运行已开始。'; self.add_event(run)
            if run.state in ('running', 'reconnecting'):
                run.last_heartbeat_at = now()

    def add_event(self, run):
        channel = next(c for c in run.config_snapshot.channels if c.channel_id == run.channel_id)
        multimodal = channel.execution_plan and channel.execution_plan.executor_kind == 'multimodal'
        event_type = ('多模态任务事件（模拟）' if multimodal else {'intrusion':'区域入侵（模拟）', 'presence':'火源出现（模拟）' if channel.target == 'fire' else '目标出现（模拟）', 'absence':'人员离岗（模拟）'}.get(channel.rule, '区域滞留（模拟）'))
        reason = (f'模拟运行事件，任务指令：{channel.execution_plan.instruction}；不表示实际视频已检测到该行为。' if multimodal else '模拟事件来自所选模板条件，不来自真实视频检测。')
        event = EventDetail(id=identifier(), agent_id=run.agent_id, run_id=run.id, revision_id=run.revision_id,
            source_id=run.source_id, channel_id=run.channel_id, occurred_at=now(), updated_at=now(), row_version=1,
            event_type=event_type, severity='warning', reason=reason,
            evidence_status='missing' if self.scenario == 'insufficient_evidence' else 'ready', review_status='unreviewed',
            start_media_ms=(run.start_media_ms or 0) if run.source_kind == 'file' else None, end_media_ms=((run.start_media_ms or 0)+1000) if run.source_kind == 'file' else None,
            evidence=[EvidenceDTO(id=identifier(), kind='image', state='missing' if self.scenario == 'insufficient_evidence' else 'ready', message='仅可展示模拟证据示意图，不是真实截图。')], feedback_history=[], data_origin='mock')
        self.event_rows[event.id] = event; self.sequence += 1; self.changes.append((self.sequence, event.id))

    def events(self, agent_id, actor_id, filters, cursor=None, after=None):
        with self.lock:
            self.check('events'); self.tick()
            limit = filters.get('limit', 30)
            pivot = None; position = 0
            try:
                if after is not None:
                    position = int(after)
                    if position < 0:
                        raise ValueError()
                elif cursor:
                    pivot = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
                    if not isinstance(pivot, list) or len(pivot) != 2 or not all(isinstance(x, str) for x in pivot):
                        raise ValueError()
            except (ValueError, TypeError, UnicodeError):
                raise Error(422, 'invalid_cursor', '分页或订阅游标无效。')
            rows = [e for e in self.event_rows.values() if e.agent_id == agent_id]
            today = datetime.now(ZoneInfo('Asia/Shanghai')).date()
            total = sum(datetime.fromisoformat(e.occurred_at.replace('Z', '+00:00')).astimezone(ZoneInfo('Asia/Shanghai')).date() == today for e in rows)
            pending = sum(e.review_status == 'unreviewed' for e in rows)
            for name in ('run_id', 'event_type', 'review_status'):
                if filters.get(name):
                    rows = [e for e in rows if getattr(e, name) == filters[name]]
            for name, comparison in [('from_time', lambda a,b: a >= b), ('to_time', lambda a,b: a <= b)]:
                if filters.get(name):
                    bound = datetime.fromisoformat(filters[name].replace('Z', '+00:00'))
                    rows = [e for e in rows if comparison(datetime.fromisoformat(e.occurred_at.replace('Z', '+00:00')), bound)]
            resync = after is not None and position > self.sequence
            stream_cursor = self.sequence
            if after is not None:
                changes = [(seq, eid) for seq, eid in self.changes if seq > position][:limit]
                ids = {eid for seq, eid in changes}
                rows = [e for e in rows if e.id in ids]
                stream_cursor = changes[-1][0] if changes else self.sequence
            elif pivot:
                rows = [e for e in rows if (e.occurred_at, e.id) < tuple(pivot)]
            rows.sort(key=lambda e: (e.occurred_at, e.id), reverse=True)
            page = rows[:limit]
            items = [AgentEventDTO.model_validate(e.model_dump(exclude={'evidence', 'feedback_history'})) for e in page]
            if self.scenario == 'duplicate_events' and items:
                items.append(items[0].model_copy(deep=True))
            next_cursor = base64.urlsafe_b64encode(json.dumps([page[-1].occurred_at, page[-1].id]).encode()).decode() if after is None and len(rows)>limit else None
            return AgentEventPage(items=items, next_cursor=next_cursor,
                stream_cursor=str(stream_cursor), updated_at=now(), data_origin='mock', resync_required=resync, today_count=total, pending_review_count=pending)

    def event(self, agent_id, event_id, actor_id):
        with self.lock:
            self.check('events')
            event = self.event_rows.get(event_id)
            if not event or event.agent_id != agent_id:
                raise Error(404, 'event_not_found', '事件不存在或不属于此智能体。')
            return event.model_copy(deep=True)

    def feedback(self, agent_id, event_id, body, actor_id, key):
        with self.lock:
            replay, hashed = self.replay(actor_id, key, f'feedback:{event_id}', body.model_dump(mode='json'))
            if replay:
                return replay
            self.event(agent_id, event_id, actor_id); event = self.event_rows[event_id]
            if event.row_version != body.row_version:
                raise Error(409, 'feedback_conflict', '该事件已由其他人核查，请刷新后再提交。')
            event.feedback_history.append(FeedbackDTO(id=identifier(), event_id=event_id, label=body.label, reason=body.reason, created_at=now(), author_id=actor_id))
            event.review_status = body.label; event.feedback_reason = body.reason; event.row_version += 1; event.updated_at = now()
            self.sequence += 1; self.changes.append((self.sequence, event_id))
            return self.remember(actor_id, key, hashed, event)

    def missed(self, agent_id, actor_id):
        self.check('events')
        with self.lock:
            return [m.model_copy(deep=True) for m in self.annotations.values() if m.agent_id == agent_id]

    def add_missed(self, run, body, actor_id, key):
        self.check('events')
        with self.lock:
            replay, hashed = self.replay(actor_id, key, 'missed', body.model_dump(mode='json'))
            if replay:
                return replay
            value = MissedDTO(**body.model_dump(), id=identifier(), agent_id=run.agent_id, revision_id=run.revision_id,
                source_id=run.source_id, channel_id=run.channel_id, evidence_message='模拟人工记录；没有真实回放证据，不计为系统检出。', created_at=now(), data_origin='mock')
            self.annotations[value.id] = value
            return self.remember(actor_id, key, hashed, value)

    def playback(self, run, actor_id):
        self.check('media')
        if run.state not in ('running', 'reconnecting', 'completed', 'stopped', 'failed'):
            raise Error(409, 'playback_unavailable', '该运行还没有可用画面。')
        with self.lock:
            value = PlaybackDTO(id=identifier(), agent_id=run.agent_id, run_id=run.id, protocol='mock', expires_at=(datetime.now(timezone.utc)+timedelta(minutes=2)).isoformat().replace('+00:00', 'Z'),
                message='模拟场景示意图，不是真实视频或检测输出。', regions=next(b.regions for c in run.config_snapshot.channels if c.channel_id == run.channel_id for b in channel_sources(c) if b.source_id == run.source_id),
                targets=[TargetBox(id='MOCK-target', label='模拟人员', x=.4, y=.25, width=.13, height=.45)] if run.state == 'running' else [], observed_at=now(), data_origin='mock',
                media_origin_ms=run.start_media_ms or 0, duration_ms=run.selected_duration_ms)
            self.sessions[value.id] = (run.agent_id, actor_id)
            return value

    def evidence(self, agent_id, event_id, evidence_id, actor_id):
        event = self.event(agent_id, event_id, actor_id)
        evidence = next((e for e in event.evidence if e.id == evidence_id), None)
        if not evidence or evidence.state != 'ready':
            raise Error(409, 'evidence_unavailable', '证据尚未生成或已不可用，不能伪造片段。')
        return PlaybackDTO(id=identifier(), agent_id=agent_id, run_id=event.run_id, protocol='mock', expires_at=(datetime.now(timezone.utc)+timedelta(minutes=2)).isoformat().replace('+00:00', 'Z'), message='模拟证据示意图，不是真实截图或录像。', data_origin='mock')

    def release_playback(self, agent_id, session_id, actor_id):
        with self.lock:
            if self.sessions.get(session_id) == (agent_id, actor_id):
                self.sessions.pop(session_id, None)

    def compare(self, baseline, candidate, actor_id):
        self.check('events')
        def counts(run):
            rows = [e for e in self.event_rows.values() if e.run_id == run.id]
            return {'system_events': len(rows), 'correct': sum(e.review_status == 'correct' for e in rows), 'false_positive': sum(e.review_status == 'false_positive' for e in rows), 'missed': sum(m.run_id == run.id for m in self.annotations.values()), 'missing_evidence': sum(e.evidence_status != 'ready' for e in rows)}
        comparable = baseline.source_kind == candidate.source_kind == 'file' and baseline.source_snapshot and candidate.source_snapshot and bool(baseline.source_snapshot.sha256) and baseline.source_snapshot.sha256 == candidate.source_snapshot.sha256 and (baseline.start_media_ms, baseline.end_media_ms) == (candidate.start_media_ms, candidate.end_media_ms) and baseline.state not in ACTIVE_STATES and candidate.state not in ACTIVE_STATES
        return ComparisonDTO(baseline_run_id=baseline.id, candidate_run_id=candidate.id, comparable=bool(comparable),
            limitation='仅对照模拟计数，不代表真实准确率。'+('模拟素材范围一致。' if comparable else '实时或不同素材/范围不可直接比较效果。'), baseline=counts(baseline), candidate=counts(candidate), data_origin='mock')

    def export(self, agent_id, body, actor_id, key):
        with self.lock:
            replay, hashed = self.replay(actor_id, key, 'export', [agent_id, body.model_dump(mode='json')])
            if replay:
                return self.export_status(agent_id, replay.id, actor_id)
            job = ExportDTO(id=identifier(), agent_id=agent_id, state='queued', message='模拟导出作业已排队，不会生成正式报告。', completed_items=0, total_items=3, data_origin='mock')
            self.jobs[job.id] = job; self.job_started[job.id] = self.clock()
            self.job_payloads[job.id] = {'WARNING': 'MOCK_NOT_A_VALIDATION_REPORT', 'data_origin': 'mock', 'snapshot_at': now(), 'requested_contents': body.contents, 'destination': body.destination, 'destination_alias': body.destination_alias, 'runs': [self.run_rows[r].model_dump(mode='json') for r in body.run_ids], 'events': [e.model_dump(mode='json') for e in self.event_rows.values() if e.run_id in body.run_ids], 'author_id': actor_id}
            return self.remember(actor_id, key, hashed, job)

    def export_destinations(self, actor_id):
        return ExportDestinations(items=[ExportDestination(kind='browser', label='当前电脑（浏览器下载）'), ExportDestination(kind='host', alias='mock-host', label='模拟服务主机目录（只演示，不写入实际目录）')], data_origin='mock')

    def export_status(self, agent_id, export_id, actor_id):
        with self.lock:
            job = self.jobs.get(export_id)
            if not job or job.agent_id != agent_id:
                raise Error(404, 'export_not_found', '导出作业不存在。')
            if job.state not in ('succeeded', 'failed', 'canceled'):
                elapsed = self.clock()-self.job_started[job.id]
                stages = ['queued', 'collecting', 'rendering', 'packaging', 'succeeded']
                stage = min(int(elapsed), 4); job.state = stages[stage]; job.completed_items = min(stage, 3)
                if self.scenario == 'export_failed' and elapsed >= 1:
                    job.state = 'failed'; job.message = '模拟导出失败，原运行和反馈保留，可以重试。'
                elif job.state == 'succeeded':
                    job.message = '演示作业完成，仅提供模拟清单，不含真实图片、片段或正式报告。'
                    if self.job_payloads[job.id]['destination'] == 'host':
                        job.download_url = None; job.message = '模拟主机保存步骤完成：仅演练状态，没有向实际目录写入正式报告或媒体。'
                    else:
                        job.download_url = f'/api/v1/agents/{agent_id}/exports/{job.id}/download'
            return job.model_copy(deep=True)

    def export_action(self, agent_id, export_id, action, actor_id, key):
        with self.lock:
            replay, hashed = self.replay(actor_id, key, f'export:{action}', [agent_id, export_id])
            if replay:
                return self.export_status(agent_id, replay.id, actor_id)
            old = self.export_status(agent_id, export_id, actor_id)
            if action == 'cancel':
                if old.state not in ('queued', 'collecting', 'rendering', 'packaging'):
                    raise Error(409, 'export_state_conflict', '该作业已经结束，不能取消。')
                self.jobs[export_id].state = 'canceled'; self.jobs[export_id].message = '模拟导出已取消，原记录保留。'
                return self.remember(actor_id, key, hashed, self.jobs[export_id])
            if old.state not in ('failed', 'canceled'):
                raise Error(409, 'export_state_conflict', '仅失败或取消的导出可以重试。')
            job = old.model_copy(update={'id': identifier(), 'state': 'queued', 'completed_items': 0, 'download_url': None, 'message': '模拟重试已排队，沿用原始导出快照。'})
            self.jobs[job.id] = job; self.job_payloads[job.id] = self.job_payloads[old.id]; self.job_started[job.id] = self.clock()
            return self.remember(actor_id, key, hashed, job)

    def export_download(self, agent_id, export_id, actor_id):
        value = self.export_status(agent_id, export_id, actor_id)
        if value.state != 'succeeded':
            raise Error(409, 'export_not_ready', '导出尚未成功，不能下载。')
        if self.job_payloads[export_id]['destination'] != 'browser':
            raise Error(409, 'export_not_ready', '这项作业选择的是主机目录，没有浏览器下载文件。')
        return 'MOCK_NOT_A_REPORT.json', 'application/json', json.dumps(self.job_payloads[export_id], ensure_ascii=False, indent=2).encode('utf-8')

    def set_scenario(self, scenario, run_id=None):
        with self.lock:
            if scenario == 'run_failed':
                run = self.run_rows.get(run_id)
                if not run or run.state not in ACTIVE_STATES:
                    raise Error(422, 'run_not_found', '请选择一个正在运行的模拟通道。')
                run.state = 'failed'; run.ended_at = now(); run.message = '模拟单路异常，其他通道不受影响。'
            self.scenario = scenario


def seed_demo(db, actor_id):
    """Synthetic fixtures only; invoked exclusively by the explicit isolated demo app."""
    from ...shared.models import Source
    from .models import AgentCommand
    from .schemas import AgentCreate
    from . import service
    from sqlalchemy import select
    key = f'MOCK-seed-v2:{actor_id}'
    previous = db.scalar(select(AgentCommand).where(AgentCommand.actor_id == actor_id, AgentCommand.command_key == key))
    if previous:
        return previous.response
    source_ids = [str(uuid5(NAMESPACE_URL, f'vision-agent-demo-v2-source-{i}')) for i in range(2)]
    for i, sid in enumerate(source_ids):
        if not db.get(Source, sid):
            db.add(Source(id=sid, name='模拟实况源（无真实媒体）' if i == 0 else '模拟录像源（无真实媒体）',
                kind='camera' if i == 0 else 'file', status='unverified' if i == 0 else 'ready', address=None,
                duration_ms=None if i == 0 else 60000, width=1280, height=720,
                sha256=None if i == 0 else 'MOCK-file-fingerprint-not-real-media'))
    db.commit()
    config = RevisionConfig(channels=[dict(channel_id=identifier(), name=f'模拟监测通道 {i+1}', source_id=sid,
        requirement_text='模拟人员在指定区域停留超过30秒时报警', target='person', rule='dwell', duration_seconds=30,
        start_media_ms=None if i == 0 else 0, end_media_ms=None if i == 0 else 60000,
        regions=[dict(id=identifier(), name='模拟监测区域', points=[[.2,.15],[.85,.15],[.85,.9],[.2,.9]])],
        capability_ref=dict(model_id='MOCK-person', model_version='1.0', template_id='MOCK-region', template_version='1.0')) for i, sid in enumerate(source_ids)])
    return service.create_agent(db, AgentCreate(name='模拟智能体：双路滞留监测', description='仅用于练习操作，不进行真实识别。', config=config), actor_id, key)
