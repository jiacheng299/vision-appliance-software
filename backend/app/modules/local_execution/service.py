"""Persistent local YOLO executor. Successful decoded frames are the only absence evidence."""
from concurrent.futures import ThreadPoolExecutor, wait
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import math
import os
from pathlib import Path
from threading import Event, RLock, Thread
import time
from zoneinfo import ZoneInfo

from sqlalchemy import select, text, delete

from ...shared.errors import Error
from ...shared.models import now, uid
from ...shared.storage import controlled_path
from ...shared.media_gateway import MediaGateway
from .. import sources, settings
from ..agents.contracts import (ACTIVE_STATES, AgentEventDTO, AgentEventPage, ChannelOperation,
    EventDetail, EvidenceDTO, ExecutionSummary, OperationDTO, PlaybackDTO, RunDTO, SourceSnapshot)
from ..agents.schemas import channel_sources
from ..models.bridge import RegistryAgentServices
from .models import LocalAgentState, LocalEvent, LocalOperation, LocalRun
from .intrusion import IntrusionRule
from .presence import PresenceRule

COMMON_PARAMETERS = {'target','rule','duration_seconds','confidence_threshold','sample_interval_seconds'}
RULE_PARAMETERS = {
    'absence': COMMON_PARAMETERS | {'min_count','alarm_interval_seconds'},
    'intrusion': COMMON_PARAMETERS | {'tracking_timeout_seconds','exit_confirmation_seconds'},
}


class LocalAgentServices(RegistryAgentServices):
    supports_multimodal_tasks = False
    supports_task_plans = False

    def __init__(self, config, sessions, model_adapter, *, detector_factory=None, reader_factory=None, gateway=None):
        self.config, self.sessions = config, sessions
        self.init_registry(sessions, model_adapter)
        self.detector_factory, self.reader_factory = detector_factory, reader_factory
        self.gateway = gateway or MediaGateway(config)
        self.owns_gateway = gateway is None
        self.lock = RLock()
        self.stops, self.futures = {}, {}
        self.pending = []
        self.started = self.closing = False
        self.process_lock = None

    @contextmanager
    def writing(self):
        with self.sessions() as db:
            db.execute(text('BEGIN IMMEDIATE'))
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    def start(self):
        with self.lock:
            if self.started: return
            # One executor owns a local DB at a time; an OS lock releases even on a process crash.
            handle = (self.config.var_root / 'local-execution.lock').open('a+b')
            if handle.tell() == 0:
                handle.write(b'0'); handle.flush()
            handle.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                handle.close()
                raise Error(503,'executor_already_running','同一数据目录已有本地检测进程，请先关闭它。') from None
            self.process_lock = handle
            try:
                with self.writing() as db:
                    for row in db.scalars(select(LocalRun).where(LocalRun.state.in_(ACTIVE_STATES))):
                        self._change(row,state='failed',ended_at=now(),error_code='executor_interrupted',
                                     message='上次检测进程已中断，请重新启动任务。')
                    self._refresh_operations(db)
                # Admission follows the saved setting; the pool is only a hard ceiling.
                self.pending = []
                self.pool = ThreadPoolExecutor(max_workers=64,thread_name_prefix='presence')
                self.started, self.closing = True, False
                self.heartbeat_stop = Event()
                self.heartbeat = Thread(target=self._heartbeat,daemon=True,name='presence-heartbeat')
                self.heartbeat.start()
            except Exception:
                self._release_lock()
                raise

    def _release_lock(self):
        if self.process_lock:
            self.process_lock.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.process_lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.process_lock.fileno(), fcntl.LOCK_UN)
            self.process_lock.close()
            self.process_lock = None

    def close(self):
        with self.lock:
            if not self.started: return
            if self.closing: return
            self.closing = True
            self.heartbeat_stop.set()
            for stop in self.stops.values(): stop.set()
            futures = list(self.futures.values())
            for future in futures: future.cancel()
            with self.writing() as db:
                for row in db.scalars(select(LocalRun).where(LocalRun.state.in_(ACTIVE_STATES))):
                    future = self.futures.get(row.id)
                    invoked = bool(row.payload.get('started_at')) or bool(future and future.running())
                    self._change(row,state='stopping' if invoked else 'canceled',
                                 ended_at=None if invoked else now(),
                                 message='应用正在关闭，本次监测已停止接收新画面。')
                self._refresh_operations(db)
        _, unfinished = wait(futures,timeout=6)
        self.heartbeat.join(timeout=2)
        self.pool.shutdown(wait=False,cancel_futures=True)
        if unfinished:
            # Threads inside native inference cannot be killed safely. Retain ownership
            # until they actually return, preventing a replacement executor overlap.
            Thread(target=self._finish_close,args=(futures,),daemon=True,name='presence-close').start()
            return
        self._finalize_close()

    def _finish_close(self, futures):
        wait(futures)
        self._finalize_close()

    def _finalize_close(self):
        with self.lock:
            if not self.started: return
            with self.writing() as db:
                for row in db.scalars(select(LocalRun).where(LocalRun.state.in_(ACTIVE_STATES))):
                    self._change(row,state='stopped' if row.payload.get('started_at') else 'canceled',ended_at=now(),message='应用已关闭，本次监测已停止。')
                self._refresh_operations(db)
            self.started = False
            self._release_lock()
            if self.owns_gateway: self.gateway.close()

    def _heartbeat(self):
        while not self.heartbeat_stop.wait(3):
            try:
                with self.writing() as db:
                    for row in db.scalars(select(LocalRun).where(LocalRun.state.in_({'starting','running','reconnecting','stopping'}))):
                        self._change(row,last_heartbeat_at=now())
                self._dispatch_pending()
            except Exception:
                # No fabricated heartbeat if storage is unavailable; workspace will mark it stale.
                continue

    def _dispatch_pending(self):
        with self.lock:
            if not self.started or self.closing:return
            with self.sessions() as db:
                limit = settings.values_for(db,'resources')['max_concurrent_jobs']
            active = sum(not future.done() for future in self.futures.values())
            while self.pending and active < limit:
                identifier = self.pending.pop(0)
                stop = self.stops[identifier]
                if stop.is_set():continue
                self.futures[identifier] = self.pool.submit(self._execute,identifier,stop)
                active += 1

    def available(self, service):
        return service in {'capability','runtime','events','media'} and self.started and not self.closing

    @staticmethod
    def _change(row, **changes):
        row.payload = {**row.payload,**changes}
        if 'state' in changes: row.state = changes['state']

    def runs(self, agent_id, actor_id):
        with self.sessions() as db:
            rows = db.scalars(select(LocalRun).where(LocalRun.agent_id==agent_id,LocalRun.actor_id==actor_id))
            return sorted((RunDTO.model_validate(r.payload) for r in rows),key=lambda r:r.created_at or '',reverse=True)

    def operation(self, agent_id, operation_id, actor_id):
        with self.sessions() as db:
            row = db.get(LocalOperation,operation_id)
            if not row or row.agent_id!=agent_id or row.actor_id!=actor_id:
                raise Error(404,'operation_not_found','运行操作不存在。')
            return OperationDTO.model_validate(row.payload)

    def _refresh_operations(self, db):
        for row in db.scalars(select(LocalOperation)):
            op = OperationDTO.model_validate(row.payload)
            if op.state in {'succeeded','partial_failed','failed','canceled'}: continue
            for item in op.channels:
                run_id = item.old_run_id if op.kind=='stop' else item.new_run_id
                run = db.get(LocalRun,run_id) if run_id else None
                if not run: continue
                if op.kind=='stop':
                    item.state = 'succeeded' if run.state not in ACTIVE_STATES else 'stopping_old'
                elif run.state in {'running','reconnecting','completed','stopping','stopped'} and run.payload.get('started_at'):
                    item.state = 'succeeded'
                elif run.state == 'failed': item.state = 'failed'
                elif run.state in {'canceled','stopped'}: item.state = 'canceled'
                else: item.state = 'starting_new' if run.state=='starting' else 'pending'
                item.message = run.payload.get('message','')
            states = {c.state for c in op.channels}
            if states <= {'succeeded'}: op.state = 'succeeded'
            elif states <= {'succeeded','failed','canceled'}:
                op.state = 'partial_failed' if 'succeeded' in states else 'failed' if 'failed' in states else 'canceled'
            else: op.state = 'running'
            row.payload = op.model_dump(mode='json')

    @staticmethod
    def _source_identity(db, source_id):
        source = sources.get_source(db,source_id)
        fields = ('id','kind','address','credentials','media_key','sha256','width','height','duration_ms')
        # Private digest only; never expose addresses or credentials in RunDTO.
        return hashlib.sha256(json.dumps({k:getattr(source,k) for k in fields},sort_keys=True).encode()).hexdigest()

    def _checked_source(self, db, snapshot, identity=None):
        source = sources.resolve_agent_source(db,snapshot.id)
        fields = {'id':source.id,'row_version':source.row_version,'kind':source.kind,'sha256':source.sha256,
                  'width':source.width,'height':source.height,'duration_ms':source.duration_ms}
        if identity is not None:
            fields['row_version'] = snapshot.row_version
        changed = [key for key,value in fields.items() if value!=getattr(snapshot,key)]
        identity_changed = identity is not None and self._source_identity(db,snapshot.id)!=identity
        if changed or identity_changed:
            logging.getLogger(__name__).warning('Source check rejected id=%s fields=%s identity_changed=%s identity_pinned=%s',
                snapshot.id,changed,identity_changed,identity is not None)
            raise Error(409,'source_changed','视频源已变化，请重新验证任务。')
        return source

    def _parameters(self, channel):
        values = {p.key:p.value for p in channel.parameters}
        allowed = RULE_PARAMETERS.get(channel.rule,set())
        if set(values)-allowed or channel.target!='person' or channel.rule not in RULE_PARAMETERS or not channel.capability_ref:
            raise Error(422,'local_capability_unsupported','当前本地执行器仅支持人员在岗和人员区域入侵监测及其声明参数。')
        if channel.rule == 'absence':
            result = dict(confidence=.5,min_count=1,duration_seconds=channel.duration_seconds or 30,
                          alarm_interval_seconds=60,sample_interval_seconds=1)
        else:
            result = dict(confidence=.5,duration_seconds=channel.duration_seconds or 8,
                          tracking_timeout_seconds=5,exit_confirmation_seconds=10,sample_interval_seconds=1)
        for key,value in values.items():
            if key in ('target','rule'):
                if value != getattr(channel,key): raise Error(422,'parameter_conflict','目标或规则与模板不一致。')
            else: result['confidence' if key=='confidence_threshold' else key] = value
        if channel.rule == 'absence' and result['min_count'] < 1:
            raise Error(422,'presence_count_invalid','在岗要求人数必须至少为1。')
        if channel.rule == 'intrusion' and result['tracking_timeout_seconds'] >= result['exit_confirmation_seconds']:
            raise Error(422,'intrusion_timing_invalid','目标跟踪超时必须小于离开确认时间。')
        if channel.rule == 'intrusion' and result['sample_interval_seconds'] >= result['tracking_timeout_seconds']:
            raise Error(422,'intrusion_sampling_invalid','分析采样间隔必须小于目标跟踪超时。')
        if result['duration_seconds'] != channel.duration_seconds:
            raise Error(422,'parameter_conflict','持续时间与任务配置不一致。')
        return result

    def submit(self, command, actor_id, key):
        request_hash = hashlib.sha256(json.dumps(command.model_dump(mode='json'),sort_keys=True,separators=(',',':')).encode()).hexdigest()
        with self.lock:
            if not self.started or self.closing: self.unavailable('runtime')
            with self.sessions() as db:
                prior = db.scalar(select(LocalOperation).where(LocalOperation.agent_id==command.agent_id,
                    LocalOperation.actor_id==actor_id,LocalOperation.command_key==key))
                if prior:
                    if prior.request_hash!=request_hash: raise Error(409,'idempotency_conflict','同一操作编号不能用于不同运行请求。')
                    return OperationDTO.model_validate(prior.payload)
            selected, prepared = [], []
            if command.kind != 'stop':
                if not command.config or not command.revision_id or not command.revision_no:
                    raise Error(422,'configuration_required','启动必须指定已发布版本。')
                selected = [c for c in command.config.channels if c.channel_id in command.channel_ids]
                if not selected or {c.channel_id for c in selected}!=set(command.channel_ids):
                    raise Error(422,'channel_not_found','监测组不存在。')
                snapshots = {s.id:s for s in command.source_snapshots}
                for channel in selected:
                    self._parameters(channel)
                    self.model_adapter.resolve_model(channel.capability_ref)
                    for binding in channel_sources(channel):
                        snapshot = snapshots.get(binding.source_id)
                        if not snapshot: raise Error(422,'source_snapshot_required','启动缺少视频源验证快照。')
                        with self.sessions() as db:
                            source = self._checked_source(db,snapshot)
                            sources.resolve_execution_input(db,self.config,source.id,self.gateway)
                            identity = self._source_identity(db,source.id)
                        if not binding.regions: raise Error(422,'region_required','人员监测需要划定区域。')
                        if source.kind=='file' and (binding.start_media_ms is None or binding.end_media_ms>source.duration_ms):
                            raise Error(422,'media_range_required','录像监测需要有效的起止时间。')
                        prepared.append((channel,binding,snapshot,identity))
                if not prepared or len(prepared)>64:
                    raise Error(422,'execution_scope_invalid','运行视频数量超出本地执行范围。')
            new_ids, stop_ids = [], []
            with self.writing() as db:
                state = db.scalar(select(LocalAgentState).where(LocalAgentState.agent_id==command.agent_id,LocalAgentState.actor_id==actor_id))
                if command.kind!='stop' and state and state.archived:
                    raise Error(409,'agent_archived','该任务已归档，请先恢复。')
                if command.kind!='stop':
                    from sqlalchemy import func
                    count = db.scalar(select(func.count()).select_from(LocalRun).where(LocalRun.state.in_(ACTIVE_STATES)))
                    if count+len(prepared)>64:
                        raise Error(429,'local_queue_full','本地检测队列已满，请停止部分任务或稍后重试。')
                active = list(db.scalars(select(LocalRun).where(LocalRun.agent_id==command.agent_id,
                    LocalRun.actor_id==actor_id,LocalRun.state.in_(ACTIVE_STATES))))
                scope = set(command.channel_ids) if command.kind!='stop' else {command.stop_channel_id} if command.stop_channel_id else None
                scoped = [r for r in active if scope is None or r.channel_id in scope]
                if command.kind!='stop' or command.stop_channel_id:
                    if {r.id for r in scoped}!=set(command.expected_active_run_ids):
                        raise Error(409,'active_runs_changed','当前运行已变化，请刷新后重试。')
                if command.kind=='start' and scoped:
                    raise Error(409,'channel_running','该监测组已有运行，请先停止。')
                if command.kind=='stop':
                    if command.stop_run_id:
                        row = db.get(LocalRun,command.stop_run_id)
                        if not row or row.agent_id!=command.agent_id or row.actor_id!=actor_id:
                            raise Error(404,'run_not_found','本次运行不存在。')
                        scoped = [row]
                    elif not command.stop_channel_id:
                        raise Error(422,'stop_scope_required','停止操作需要指定运行或监测组。')
                for row in scoped:
                    stop_ids.append(row.id)
                    if row.state in ACTIVE_STATES: self._change(row,state='stopping',message='正在停止本次监测。')
                items = [ChannelOperation(channel_id=r.channel_id,source_id=r.source_id,state='stopping_old',old_run_id=r.id) for r in scoped] if command.kind=='stop' else []
                for channel,binding,snapshot,identity in prepared:
                    identifier = uid()
                    dto = RunDTO(id=identifier,agent_id=command.agent_id,revision_id=command.revision_id,
                        revision_no=command.revision_no,channel_id=channel.channel_id,channel_name=channel.name,
                        source_id=binding.source_id,state='queued',created_at=now(),source_kind=snapshot.kind,
                        recording_available=snapshot.kind=='file',config_snapshot=command.config,source_snapshot=snapshot,
                        start_media_ms=binding.start_media_ms,end_media_ms=binding.end_media_ms,
                        selected_duration_ms=(binding.end_media_ms-binding.start_media_ms) if binding.end_media_ms is not None else None,
                        baseline_run_id=command.baseline_run_id,message='等待本地检测资源。')
                    predecessors = [r.id for r in scoped if r.channel_id==channel.channel_id] if command.kind=='apply' else []
                    db.add(LocalRun(id=identifier,agent_id=command.agent_id,actor_id=actor_id,channel_id=channel.channel_id,
                        source_id=binding.source_id,state='queued',payload=dto.model_dump(mode='json'),observation={'source_identity':identity},predecessors=predecessors))
                    items.append(ChannelOperation(channel_id=channel.channel_id,source_id=binding.source_id,state='pending',
                        old_run_id=next(iter(predecessors),None),new_run_id=identifier))
                    new_ids.append(identifier)
                operation = OperationDTO(id=uid(),agent_id=command.agent_id,kind=command.kind,state='pending',channels=items)
                db.add(LocalOperation(id=operation.id,agent_id=command.agent_id,actor_id=actor_id,command_key=key,
                    request_hash=request_hash,payload=operation.model_dump(mode='json')))
                db.flush()
                self._refresh_operations(db)
            for identifier in stop_ids:
                stop = self.stops.get(identifier)
                if stop: stop.set()
                future = self.futures.get(identifier)
                if future and future.cancel(): self._finish(identifier,'canceled','尚未开始的监测已取消。')
                elif future is None:self._finish(identifier,'canceled','尚未开始的监测已取消。')
            for identifier in new_ids:
                self.stops[identifier] = Event()
                self.pending.append(identifier)
            self._dispatch_pending()
            return self.operation(command.agent_id,operation.id,actor_id)

    def set_archived(self, agent_id, archived, actor_id):
        with self.lock, self.writing() as db:
            if archived and db.scalar(select(LocalRun.id).where(LocalRun.agent_id==agent_id,LocalRun.actor_id==actor_id,LocalRun.state.in_(ACTIVE_STATES)).limit(1)):
                raise Error(409,'active_runs_exist','请先停止该任务的运行，再归档。')
            row = db.scalar(select(LocalAgentState).where(LocalAgentState.agent_id==agent_id,LocalAgentState.actor_id==actor_id))
            if row: row.archived = int(archived)
            else: db.add(LocalAgentState(id=uid(),agent_id=agent_id,actor_id=actor_id,archived=int(archived)))

    @contextmanager
    def deleting_task(self, agent_id, actor_id):
        keys, identifiers = [], []
        with self.lock:
            if not self.started or self.closing:self.unavailable('runtime')
            with self.writing() as db:
                state=db.scalar(select(LocalAgentState).where(LocalAgentState.agent_id==agent_id,LocalAgentState.actor_id==actor_id))
                was_archived=bool(state and state.archived)
                if state:state.archived=1
                else:db.add(LocalAgentState(id=uid(),agent_id=agent_id,actor_id=actor_id,archived=1))
                identifiers=list(db.scalars(select(LocalRun.id).where(LocalRun.agent_id==agent_id,LocalRun.actor_id==actor_id)))
            try:
                futures=[]
                for identifier in identifiers:
                    stop=self.stops.get(identifier)
                    if stop:stop.set()
                    future=self.futures.get(identifier)
                    if future:future.cancel();futures.append(future)
                self.pending[:]=[i for i in self.pending if i not in identifiers]
                if wait(futures,timeout=10)[1]:
                    raise Error(409,'task_stop_timeout','监测尚未完全停止，任务未删除，请稍后重试。')
                def purge(db):
                    keys.extend(db.scalars(select(LocalEvent.evidence_key).where(LocalEvent.agent_id==agent_id,LocalEvent.actor_id==actor_id,LocalEvent.evidence_key.is_not(None))))
                    for model in (LocalEvent,LocalOperation,LocalRun,LocalAgentState):
                        db.execute(delete(model).where(model.agent_id==agent_id,model.actor_id==actor_id))
                yield purge
            except Exception:
                with self.writing() as db:
                    state=db.scalar(select(LocalAgentState).where(LocalAgentState.agent_id==agent_id,LocalAgentState.actor_id==actor_id))
                    if state:state.archived=int(was_archived)
                raise
            for identifier in identifiers:
                self.stops.pop(identifier,None);self.futures.pop(identifier,None)
        for key in keys:
            try:controlled_path(self.config,'media',key).unlink(missing_ok=True)
            except OSError:logging.getLogger(__name__).warning('Deleted task evidence cleanup failed')

    def _finish(self, identifier, state, message, code=None):
        with self.writing() as db:
            row = db.get(LocalRun,identifier)
            if row and row.state in ACTIVE_STATES:
                self._change(row,state=state,ended_at=now(),last_heartbeat_at=now(),message=message,error_code=code)
                self._refresh_operations(db)

    def _execute(self, identifier, stop):
        rule = None
        try:
            with self.sessions() as db:
                row = db.get(LocalRun,identifier)
                run = RunDTO.model_validate(row.payload)
                predecessors = list(row.predecessors)
                source_identity = row.observation.get('source_identity')
            deadline = time.monotonic()+20
            while predecessors and not stop.is_set():
                with self.sessions() as db:
                    predecessors = [rid for rid in predecessors if (old:=db.get(LocalRun,rid)) and old.state in ACTIVE_STATES]
                if predecessors and time.monotonic()>=deadline:
                    raise Error(409,'previous_run_not_stopped','旧版本未能及时停止，请重试。')
                if predecessors: stop.wait(.1)
            if stop.is_set():
                self._finish(identifier,'canceled','尚未开始的监测已取消。'); return
            channel = next(c for c in run.config_snapshot.channels if c.channel_id==run.channel_id)
            binding = next(s for s in channel_sources(channel) if s.source_id==run.source_id)
            parameters = self._parameters(channel)
            path = self.model_adapter.resolve_model(channel.capability_ref)
            detector_factory = self.detector_factory
            if detector_factory is None:
                from ..models.yolo import YoloPersonDetector
                detector_factory = YoloPersonDetector
            reader_factory = self.reader_factory
            if reader_factory is None:
                from .reader import VideoFrameReader
                reader_factory = VideoFrameReader
            detector = detector_factory(path,confidence=parameters['confidence'])
            interval = parameters['sample_interval_seconds']
            if channel.rule == 'absence':
                rule = PresenceRule([r.points for r in binding.regions],min_count=parameters['min_count'],
                    duration_seconds=parameters['duration_seconds'],alarm_interval_seconds=parameters['alarm_interval_seconds'],
                    max_gap_seconds=max(3,interval*1.5))
            else:
                rule = IntrusionRule([r.points for r in binding.regions],entry_seconds=parameters['duration_seconds'],
                    occlusion_seconds=parameters['tracking_timeout_seconds'],
                    exit_seconds=parameters['exit_confirmation_seconds'],
                    max_gap_seconds=min(parameters['tracking_timeout_seconds'],max(1.5,interval*1.5)))
            with self.writing() as db:
                row = db.get(LocalRun,identifier)
                if row.state not in ACTIVE_STATES: return
                self._change(row,state='starting',last_heartbeat_at=now(),message='正在读取视频并初始化人员检测。')
                resources = settings.values_for(db,'resources')
                self._refresh_operations(db)
            failures, observed = 0, False
            while not stop.is_set():
                try:
                    with self.sessions() as db:
                        self._checked_source(db,run.source_snapshot,source_identity)
                        source, locator = sources.resolve_execution_input(db,self.config,run.source_id,self.gateway)
                    with reader_factory(self.config,locator=locator,kind=run.source_kind,width=source.width,
                        height=source.height,interval=interval,start_ms=binding.start_media_ms or 0,
                        end_ms=binding.end_media_ms,stop=stop) as reader:
                        last_timestamp = None
                        last_source_check = time.monotonic()
                        for timestamp,frame in reader.frames():
                            if stop.is_set(): break
                            if time.monotonic()-last_source_check>=2:
                                with self.sessions() as db: self._checked_source(db,run.source_snapshot,source_identity)
                                last_source_check = time.monotonic()
                            detected = detector.detect(frame)
                            boxes = rule.targets_in_regions(detected) if channel.rule == 'absence' else detected
                            if stop.is_set(): break
                            observation = rule.observe(timestamp,boxes)
                            stamp = now()
                            if channel.rule == 'absence':
                                message = f'区域内 {observation.count} 人；已连续缺岗 {observation.absent_seconds:.1f} 秒。'
                                targets = [{key:box[key] for key in ('label','x','y','width','height')}|{'id':f'person-{i}'}
                                           for i,box in enumerate(boxes)]
                            else:
                                labels = {'waiting_clear':'等待区域连续清空后布防','armed':'区域已布防',
                                          'confirming':'正在确认入侵','occluded':'目标短暂遮挡，确认计时暂停',
                                          'alarmed':'本次区域入侵已报警'}
                                message = f'区域内 {observation.count} 人；{labels[observation.phase]}；有效确认 {observation.confirmed_seconds:.1f} 秒。'
                                targets = [{key:target.box[key] for key in ('label','x','y','width','height')}|{'id':target.id}
                                           for target in observation.targets]
                            with self.writing() as db:
                                row = db.get(LocalRun,identifier)
                                if row.state not in ACTIVE_STATES or row.state=='stopping': stop.set(); break
                                self._change(row,state='running',started_at=row.payload.get('started_at') or stamp,
                                    last_heartbeat_at=stamp,processed_media_ms=round(timestamp*1000) if run.source_kind=='file' else None,
                                    message=message)
                                row.observation = {'observed_at':stamp,'timestamp':timestamp,'count':observation.count,
                                    'targets':targets}
                                self._refresh_operations(db)
                            observed, failures, last_timestamp = True, 0, timestamp
                            if channel.rule == 'absence' and (observation.transition or observation.alarm) and not stop.is_set():
                                self._record_transition_event(run,observation,timestamp,frame,boxes,binding,stop,source_identity)
                            elif channel.rule == 'intrusion' and observation.alarm and not stop.is_set():
                                self._record_intrusion_event(run,observation,timestamp,frame,boxes,binding,stop,source_identity)
                    if stop.is_set(): break
                    if run.source_kind=='file':
                        if not observed or last_timestamp is None or (binding.end_media_ms is not None
                            and last_timestamp*1000+max(interval*1000,250)<binding.end_media_ms):
                            raise Error(422,'video_decode_failed','录像未能完整解码到所选范围。')
                        summary = '人员在岗' if channel.rule == 'absence' else '人员区域入侵'
                        self._finish(identifier,'completed',f'所选录像已完成真实{summary}分析。')
                        return
                    raise Error(503,'camera_frame_timeout','摄像头视频已中断。')
                except Exception as exc:
                    rule.mark_unavailable()
                    if stop.is_set(): break
                    # Only live transport failures reconnect. Changed source/model configuration must be revalidated.
                    code = getattr(exc,'code','video_decode_failed')
                    retryable = code in {'camera_frame_timeout','dependency_unavailable','media_source_not_published','camera_probe_failed','source_not_ready'}
                    if run.source_kind=='camera' and retryable and failures<resources['reconnect_attempts']:
                        failures += 1
                        with self.writing() as db:
                            row = db.get(LocalRun,identifier)
                            if row.state=='stopping': stop.set(); break
                            reset = '缺岗计时已清空' if channel.rule == 'absence' else '入侵状态已清空，恢复后等待区域清空重新布防'
                            self._change(row,state='reconnecting',last_heartbeat_at=now(),message=f'视频中断，正在重连（{failures}/{resources["reconnect_attempts"]}）；{reset}。')
                            row.observation = {}
                        stop.wait(min(2**failures,5))
                        continue
                    raise
            self._finish(identifier,'stopped','本次监测已停止。')
        except Exception as exc:
            if rule: rule.mark_unavailable()
            if stop.is_set(): self._finish(identifier,'stopped','本次监测已停止。')
            else:
                code = getattr(exc,'code','local_inference_failed')
                allowed = {'video_decode_failed','camera_frame_timeout','source_changed','source_not_found','source_unavailable',
                    'source_not_ready','source_media_missing','dependency_unavailable','media_source_not_published',
                    'previous_run_not_stopped','model_unavailable','model_file_changed','model_not_found'}
                message = {'source_changed':'视频源地址、凭据或媒体信息已改变，请核对后重新监测。',
                    'camera_frame_timeout':'摄像头持续断流，多次重连后仍无法读取画面，请检查推流服务。',
                    'source_not_ready':'摄像头未恢复在线，请测试连接后重新监测。',
                    'dependency_unavailable':'本地视频解码工具不可用，请检查 FFmpeg 配置。'}.get(code,
                    '视频读取或人员检测失败，请检查视频源与模型后重试。')
                self._finish(identifier,'failed',message,code if code in allowed else 'local_inference_failed')

    def _save_evidence(self, run, frame, boxes, binding, count, event_type):
        import cv2
        import numpy as np
        image = frame.copy()
        height,width = image.shape[:2]
        for region in binding.regions:
            points = np.array([(round(x*(width-1)),round(y*(height-1))) for x,y in region.points],dtype=np.int32)
            cv2.polylines(image,[points],True,(0,180,255),2)
        for box in boxes:
            x,y,w,h = (box[k] for k in ('x','y','width','height'))
            cv2.rectangle(image,(round(x*width),round(y*height)),(round((x+w)*width),round((y+h)*height)),(0,200,0),2)
        title, color = {
            'person_presence_restored': ('PERSON PRESENCE RESTORED',(0,180,0)),
            'person_intrusion': ('PERSON INTRUSION',(0,0,255)),
        }.get(event_type,('PERSON ABSENCE',(0,0,255)))
        cv2.putText(image,f'{title} | count={count}',(12,25),cv2.FONT_HERSHEY_SIMPLEX,.55,color,2)
        ok, encoded = cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,85])
        if not ok: raise ValueError('Image encoding failed')
        key = f'local-evidence/{run.id}/{uid()}.jpg'
        path = controlled_path(self.config,'media',key)
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary = path.with_suffix('.tmp')
        try:
            temporary.write_bytes(encoded.tobytes())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return key

    def _record_transition_event(self, run, observation, timestamp, frame, boxes, binding, stop, source_identity=None):
        restored = observation.transition == 'restored'
        duration = observation.present_seconds if restored else observation.absent_seconds
        event_type = 'person_presence_restored' if restored else 'person_absence'
        key = None
        try:
            key = self._save_evidence(run,frame,boxes,binding,observation.count,event_type)
        except Exception:
            pass  # A genuine detection remains visible when evidence storage fails.
        try:
            with self.writing() as db:
                row = db.get(LocalRun,run.id)
                if stop.is_set() or row.state!='running':
                    if key: controlled_path(self.config,'media',key).unlink(missing_ok=True)
                    return
                self._checked_source(db,run.source_snapshot,source_identity)
                stamp, identifier, evidence_id = now(), uid(), uid()
                if observation.transition == 'absence':
                    self._change(row,alert_state='absence',alert_started_at=stamp)
                elif restored:
                    self._change(row,alert_state='normal',alert_started_at=None)
                severity = 'info' if restored else 'warning'
                reason = (f'监测区域内人数已恢复至 {observation.count}，已连续在岗 {duration:.1f} 秒。'
                    if restored else f'监测区域内人数为 {observation.count}，已连续缺岗 {duration:.1f} 秒。')
                event = EventDetail(id=identifier,agent_id=run.agent_id,run_id=run.id,revision_id=run.revision_id,
                    source_id=run.source_id,channel_id=run.channel_id,occurred_at=stamp,updated_at=stamp,row_version=1,
                    event_type=event_type,severity=severity,reason=reason,
                    evidence_status='ready' if key else 'failed',review_status='unreviewed',
                    start_media_ms=round(max(binding.start_media_ms or 0,timestamp*1000-duration*1000)) if run.source_kind=='file' else None,
                    end_media_ms=round(timestamp*1000) if run.source_kind=='file' else None,
                    evidence=[EvidenceDTO(id=evidence_id,kind='image',state='ready' if key else 'failed',message='YOLO 实际分析帧与监测区域。' if key else '事件已保存，截图写入失败。')],feedback_history=[])
                db.add(LocalEvent(id=identifier,agent_id=run.agent_id,actor_id=row.actor_id,run_id=run.id,
                                  payload=event.model_dump(mode='json'),evidence_key=key))
        except Exception:
            if key: controlled_path(self.config,'media',key).unlink(missing_ok=True)
            raise

    def _record_intrusion_event(self, run, observation, timestamp, frame, boxes, binding, stop, source_identity=None):
        event_type = 'person_intrusion'
        key = None
        try:
            key = self._save_evidence(run,frame,boxes,binding,observation.count,event_type)
        except Exception:
            pass  # A genuine detection remains visible when evidence storage fails.
        try:
            with self.writing() as db:
                row = db.get(LocalRun,run.id)
                if stop.is_set() or row.state!='running':
                    if key: controlled_path(self.config,'media',key).unlink(missing_ok=True)
                    return
                self._checked_source(db,run.source_snapshot,source_identity)
                stamp, identifier, evidence_id = now(), uid(), uid()
                elapsed = observation.confirmed_seconds
                reason = f'人员进入监测区域并连续确认 {elapsed:.1f} 秒。'
                event = EventDetail(id=identifier,agent_id=run.agent_id,run_id=run.id,revision_id=run.revision_id,
                    source_id=run.source_id,channel_id=run.channel_id,occurred_at=stamp,updated_at=stamp,row_version=1,
                    event_type=event_type,severity='warning',reason=reason,
                    evidence_status='ready' if key else 'failed',review_status='unreviewed',
                    start_media_ms=round(max(binding.start_media_ms or 0,timestamp*1000-elapsed*1000)) if run.source_kind=='file' else None,
                    end_media_ms=round(timestamp*1000) if run.source_kind=='file' else None,
                    evidence=[EvidenceDTO(id=evidence_id,kind='image',state='ready' if key else 'failed',message='YOLO 实际分析帧与监测区域。' if key else '报警已保存，截图写入失败。')],feedback_history=[])
                db.add(LocalEvent(id=identifier,agent_id=run.agent_id,actor_id=row.actor_id,run_id=run.id,
                                  payload=event.model_dump(mode='json'),evidence_key=key))
        except Exception:
            if key: controlled_path(self.config,'media',key).unlink(missing_ok=True)
            raise

    @staticmethod
    def _cursor(agent_id, actor_id, kind, filters=None, sequence=None):
        identity = json.dumps([agent_id,actor_id,kind,filters or {}],sort_keys=True,separators=(',',':'))
        prefix = hashlib.sha256(identity.encode()).hexdigest()[:24]
        return prefix if sequence is None else f'{prefix}:{sequence}'

    def _parse_cursor(self, value, agent_id, actor_id, kind, filters=None):
        if value is None: return None
        prefix = self._cursor(agent_id,actor_id,kind,filters)
        try:
            head, raw = value.split(':')
            if head!=prefix or not raw.isdigit() or len(raw)>19: raise ValueError()
            return int(raw)
        except (ValueError,AttributeError):
            raise Error(422,'invalid_cursor','事件游标无效，请重新加载列表。') from None

    @staticmethod
    def _today():
        local = datetime.now(ZoneInfo('Asia/Shanghai')).replace(hour=0,minute=0,second=0,microsecond=0)
        return local.astimezone(timezone.utc).isoformat().replace('+00:00','Z')

    def events(self, agent_id, actor_id, filters, cursor=None, after=None):
        from sqlalchemy import func
        selected = {k:v for k,v in filters.items() if k!='limit' and v is not None and v!=''}
        page_sequence = self._parse_cursor(cursor,agent_id,actor_id,'page',selected)
        after_sequence = self._parse_cursor(after,agent_id,actor_id,'stream')
        limit = min(max(int(filters.get('limit',100)),1),100)
        base = select(LocalEvent).where(LocalEvent.agent_id==agent_id,LocalEvent.actor_id==actor_id)
        query = base
        for name in ('run_id','event_type','review_status'):
            if selected.get(name): query = query.where(LocalEvent.payload[name].as_string()==selected[name])
        if selected.get('from_time'): query = query.where(LocalEvent.payload['occurred_at'].as_string()>=selected['from_time'])
        if selected.get('to_time'): query = query.where(LocalEvent.payload['occurred_at'].as_string()<=selected['to_time'])
        if page_sequence is not None: query = query.where(LocalEvent.sequence<page_sequence)
        if after_sequence is not None: query = query.where(LocalEvent.sequence>after_sequence)
        with self.sessions() as db:
            # Freeze the stream boundary before reading rows. A concurrent event above
            # this boundary remains eligible for the next request.
            maximum = db.scalar(select(func.max(LocalEvent.sequence)).where(LocalEvent.agent_id==agent_id,LocalEvent.actor_id==actor_id)) or 0
            query = query.where(LocalEvent.sequence<=maximum).order_by(
                LocalEvent.sequence.asc() if after_sequence is not None else LocalEvent.sequence.desc()).limit(limit+1)
            rows = list(db.scalars(query))
            today = db.scalar(select(func.count()).select_from(base.where(LocalEvent.payload['occurred_at'].as_string()>=self._today()).subquery()))
            pending = db.scalar(select(func.count()).select_from(base.where(LocalEvent.payload['review_status'].as_string()=='unreviewed').subquery()))
        items = rows[:limit]
        sequence = (items[-1].sequence if len(rows)>limit else maximum) if after_sequence is not None else maximum
        return AgentEventPage(items=[AgentEventDTO.model_validate({k:v for k,v in r.payload.items() if k not in {'evidence','feedback_history'}}) for r in items],
            next_cursor=self._cursor(agent_id,actor_id,'page',selected,items[-1].sequence) if len(rows)>limit and after_sequence is None else None,
            stream_cursor=self._cursor(agent_id,actor_id,'stream',sequence=sequence),updated_at=now(),today_count=today,pending_review_count=pending)

    def event(self, agent_id, event_id, actor_id):
        with self.sessions() as db:
            row = db.scalar(select(LocalEvent).where(LocalEvent.id==event_id,LocalEvent.agent_id==agent_id,LocalEvent.actor_id==actor_id))
            if not row: raise Error(404,'event_not_found','报警事件不存在。')
            return EventDetail.model_validate(row.payload)

    def missed(self, agent_id, actor_id):
        return []

    def summary(self, actor_id):
        from sqlalchemy import func
        with self.sessions() as db:
            counts = dict(db.execute(select(LocalRun.state,func.count()).where(LocalRun.actor_id==actor_id).group_by(LocalRun.state)).all())
            event_rows = list(db.scalars(select(LocalEvent).where(LocalEvent.actor_id==actor_id).order_by(LocalEvent.sequence.desc()).limit(5)))
            today = db.scalar(select(func.count()).select_from(LocalEvent).where(LocalEvent.actor_id==actor_id,LocalEvent.payload['occurred_at'].as_string()>=self._today()))
        return ExecutionSummary(active_runs=sum(counts.get(s,0) for s in ACTIVE_STATES),
            running=sum(counts.get(s,0) for s in ('running','reconnecting','stopping')),
            waiting=sum(counts.get(s,0) for s in ('queued','starting')),completed=counts.get('completed',0),failed=counts.get('failed',0),
            today_events=today,recent_events=[AgentEventDTO.model_validate({k:v for k,v in r.payload.items() if k not in {'evidence','feedback_history'}}) for r in event_rows])

    def playback(self, run, actor_id):
        with self.sessions() as db:
            row = db.get(LocalRun,run.id)
            if not row or row.actor_id!=actor_id or row.agent_id!=run.agent_id: raise Error(404,'run_not_found','运行记录不存在。')
            source, _ = sources.resolve_execution_input(db,self.config,run.source_id,self.gateway)
            observed = dict(row.observation)
        channel = next(c for c in run.config_snapshot.channels if c.channel_id==run.channel_id)
        binding = next(s for s in channel_sources(channel) if s.source_id==run.source_id)
        return PlaybackDTO(id=uid(),agent_id=run.agent_id,run_id=run.id,protocol='file' if source.kind=='file' else 'hls',
            playback_url=f'/api/v1/sources/{source.id}/media' if source.kind=='file' else f'/api/v1/sources/{source.id}/live/index.m3u8',
            expires_at=(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat().replace('+00:00','Z'),
            regions=binding.regions,targets=observed.get('targets',[]) if source.kind=='camera' else [],
            observed_at=observed.get('observed_at') if source.kind=='camera' else None,
            # File endpoint serves the original full recording. Positions already refer to its media clock.
            media_origin_ms=0,duration_ms=source.duration_ms,message='真实视频；黄色区域为监测范围。')

    def evidence(self, agent_id, event_id, evidence_id, actor_id):
        detail = self.event(agent_id,event_id,actor_id)
        if not any(e.id==evidence_id and e.state=='ready' for e in detail.evidence):
            raise Error(404,'evidence_not_found','截图证据不可用。')
        return PlaybackDTO(id=uid(),agent_id=agent_id,run_id=detail.run_id,protocol='file',
            playback_url=f'/api/v1/agents/{agent_id}/events/{event_id}/evidence/{evidence_id}/media',
            expires_at=(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat().replace('+00:00','Z'))

    def evidence_file(self, agent_id, event_id, evidence_id, actor_id):
        self.evidence(agent_id,event_id,evidence_id,actor_id)
        with self.sessions() as db:
            row = db.scalar(select(LocalEvent).where(LocalEvent.id==event_id,LocalEvent.agent_id==agent_id,LocalEvent.actor_id==actor_id))
            if not row or not row.evidence_key: raise Error(404,'evidence_not_found','截图证据不可用。')
            path = controlled_path(self.config,'media',row.evidence_key)
            if not path.is_file(): raise Error(404,'evidence_not_found','截图证据已丢失。')
            return path

    def release_playback(self, agent_id, session_id, actor_id):
        # File and same-origin HLS sessions allocate no per-browser gateway resources.
        return None
