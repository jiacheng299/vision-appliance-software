"""Real executor lifecycle contract; injectable decoder/detector keep unit tests offline."""
import time
from pathlib import Path
from threading import Event
import json
import sqlite3

import pytest
from sqlalchemy import select

from app.shared.config import Config
from app.shared.db import make_engine, migrate, session_factory
from app.shared.errors import Error
from app.shared.models import Source
from app.modules.agents.contracts import RuntimeCommand, SourceSnapshot
from app.modules.agents.schemas import RevisionConfig
from app.modules.local_execution.service import LocalAgentServices


class Adapter:
    def is_ready(self): return True
    def resolve_model(self, reference): return Path('trusted.onnx')
    def deployments(self): return []


class Detector:
    def __init__(self, path, confidence=.5): pass
    def detect(self, frame): return frame


class Reader:
    frames_to_read = [(0., []), (15., []), (30., []), (45., [])]
    failure = False
    def __init__(self, *args, **kwargs): self.stop = kwargs['stop']
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def frames(self):
        for timestamp, frame in self.frames_to_read:
            if self.stop.is_set(): return
            yield timestamp, frame
        if self.failure: raise RuntimeError('private path or credentials must never escape')


@pytest.fixture
def runtime(tmp_path):
    config = Config(var_root=tmp_path, agent_demo=False)
    config.prepare()
    engine = make_engine(config)
    migrate(engine)
    sessions = session_factory(engine)
    from app.modules import settings
    with sessions() as db:
        settings.initialize(db)
        db.add(Source(id='video', name='录像', kind='file', status='ready',
                      width=640, height=480, duration_ms=60000, sha256='abc', media_key='sample.mp4'))
        db.commit()
    (tmp_path / 'media' / 'sample.mp4').write_bytes(b'controlled fixture')
    class Frames(Reader): pass
    service = LocalAgentServices(config, sessions, Adapter(), detector_factory=Detector, reader_factory=Frames)
    service.start()
    yield service, sessions, Frames, config
    service.close()
    engine.dispose()


PERSON = {'label':'person','x':.2,'y':.2,'width':.2,'height':.5,'confidence':.9}


def command(duration_seconds=30, alarm_interval_seconds=60):
    config = RevisionConfig(channels=[dict(channel_id='channel', name='岗位', target='person', rule='absence',
        duration_seconds=duration_seconds, sources=[dict(source_id='video', start_media_ms=0, end_media_ms=60000,
        regions=[dict(id='roi', points=[(0,0),(1,0),(1,1),(0,1)])])],
        capability_ref=dict(model_id='model',model_version='1',template_id='template',template_version='1'),
        parameters=[dict(key='sample_interval_seconds',value=15),dict(key='confidence_threshold',value=.5),
                    dict(key='alarm_interval_seconds',value=alarm_interval_seconds)])])
    return RuntimeCommand(kind='start',agent_id='agent',revision_id='revision',revision_no=1,config=config,
        channel_ids=['channel'],source_kinds={'video':'file'},
        source_snapshots=[SourceSnapshot(id='video',row_version=1,kind='file',sha256='abc',width=640,height=480,duration_ms=60000)])


def intrusion_command():
    config = RevisionConfig(channels=[dict(channel_id='intrusion-channel', name='禁区', target='person', rule='intrusion',
        duration_seconds=8, sources=[dict(source_id='video', start_media_ms=0, end_media_ms=20000,
        regions=[dict(id='roi', points=[(0,0),(1,0),(1,1),(0,1)])])],
        capability_ref=dict(model_id='intrusion-model',model_version='1',template_id='intrusion-template',template_version='1'),
        parameters=[dict(key='sample_interval_seconds',value=1),dict(key='confidence_threshold',value=.5),
                    dict(key='tracking_timeout_seconds',value=5),dict(key='exit_confirmation_seconds',value=10)])])
    return RuntimeCommand(kind='start',agent_id='intrusion-agent',revision_id='intrusion-revision',revision_no=1,
        config=config,channel_ids=['intrusion-channel'],source_kinds={'video':'file'},
        source_snapshots=[SourceSnapshot(id='video',row_version=1,kind='file',sha256='abc',width=640,height=480,duration_ms=60000)])


def finish(service, operation):
    deadline = time.monotonic()+5
    while time.monotonic() < deadline:
        runs = service.runs(operation.agent_id,'actor')
        if runs and all(r.state not in {'queued','starting','running','stopping','reconnecting'} for r in runs):
            return runs[0]
        time.sleep(.01)
    pytest.fail('executor failed to settle')


def test_real_absence_event_and_run_are_persistent_and_idempotent(runtime):
    service, sessions, _, config = runtime
    op = service.submit(command(), 'actor', 'start-key')
    run = finish(service, op)
    assert run.state == 'completed' and run.data_origin == 'real'
    assert run.processed_media_ms == 45000
    again = service.submit(command(), 'actor', 'start-key')
    assert again.id == op.id and len(service.runs('agent','actor')) == 1
    page = service.events('agent','actor',{'limit':100})
    assert len(page.items) == 1 and page.items[0].event_type == 'person_absence'
    event = service.event('agent', page.items[0].id, 'actor')
    assert event.run_id == run.id and event.revision_id == 'revision' and event.start_media_ms == 0
    assert event.end_media_ms == 30000 and event.data_origin == 'real'
    service.close()
    second = LocalAgentServices(config,sessions,Adapter(),detector_factory=Detector,reader_factory=Reader)
    second.start()
    try:
        assert second.runs('agent','actor')[0].id == run.id
        assert second.events('agent','actor',{'limit':100}).items[0].id == event.id
        assert second.summary('actor').today_events == 1
    finally: second.close()


def test_absence_and_recovery_are_persisted_once(runtime):
    service, _, reader, _ = runtime
    reader.frames_to_read = [
        (0., []), (1., []), (2., []),
        (3., [PERSON]), (4., [PERSON]), (5., [PERSON]),
        (6., [PERSON]),
    ]
    run = finish(service, service.submit(command(duration_seconds=2), 'actor', 'cycle'))
    events = list(reversed(service.events('agent', 'actor', {'limit':100}).items))
    assert [event.event_type for event in events] == [
        'person_absence', 'person_presence_restored'
    ]
    assert [event.severity for event in events] == ['warning', 'info']
    assert run.alert_state == 'normal'
    assert run.alert_started_at is None


def test_sustained_absence_repeats_at_the_configured_interval(runtime):
    service, _, reader, _ = runtime
    reader.frames_to_read = [
        (0., []), (1., []), (2., []),
        (3., []), (4., []), (5., []), (6., []),
    ]
    finish(service, service.submit(
        command(duration_seconds=2, alarm_interval_seconds=2),
        'actor', 'repeated-absence',
    ))
    events = list(reversed(service.events('agent', 'actor', {'limit':100}).items))
    assert [event.event_type for event in events] == [
        'person_absence', 'person_absence', 'person_absence'
    ]


def test_live_run_persists_absence_state_independently_of_event_page(runtime):
    service, _, reader, _ = runtime
    entered = Event()
    def live_frames(self):
        yield 0., []
        yield 1., []
        yield 2., []
        entered.set()
        while not self.stop.wait(.02):
            pass
    reader.frames = live_frames
    service.submit(command(duration_seconds=2), 'actor', 'live-absence')
    deadline = time.monotonic()+3
    run = None
    while time.monotonic() < deadline:
        runs = service.runs('agent', 'actor')
        if runs and runs[0].alert_state == 'absence':
            run = runs[0]
            break
        time.sleep(.01)
    assert entered.wait(1)
    assert run is not None and run.alert_started_at is not None
    assert service.events('agent', 'actor', {'limit':1}).items[0].event_type == 'person_absence'
    stop = RuntimeCommand(kind='stop', agent_id='agent', stop_run_id=run.id)
    assert finish(service, service.submit(stop, 'actor', 'live-stop')).alert_state == 'absence'


def test_failed_event_transaction_rolls_back_alert_and_removes_evidence(runtime, monkeypatch):
    service, sessions, reader, config = runtime
    from sqlalchemy import event as sqlalchemy_event
    from app.shared.storage import controlled_path
    key = 'local-evidence/failed-write/evidence.jpg'
    evidence_path = controlled_path(config, 'media', key)
    def save_evidence(*args, **kwargs):
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_bytes(b'evidence')
        return key
    monkeypatch.setattr(service, '_save_evidence', save_evidence)
    def fail_event_insert(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith('INSERT') and 'LOCAL_EVENTS' in statement.upper():
            raise sqlite3.OperationalError('injected event transaction failure')
    engine = sessions.kw['bind']
    sqlalchemy_event.listen(engine, 'before_cursor_execute', fail_event_insert)
    reader.frames_to_read = [(0., []), (1., []), (2., [])]
    try:
        run = finish(service, service.submit(command(duration_seconds=2), 'actor', 'failed-event-write'))
    finally:
        sqlalchemy_event.remove(engine, 'before_cursor_execute', fail_event_insert)
    assert run.state == 'failed'
    assert run.alert_state == 'normal'
    assert run.alert_started_at is None
    assert service.events('agent', 'actor', {'limit':100}).items == []
    assert not evidence_path.exists()


def test_real_intrusion_waits_for_clear_and_confirmation_then_records_one_event(runtime):
    service, _, reader, _ = runtime
    person = {'label':'person','x':.4,'y':.2,'width':.2,'height':.6,'confidence':.9}
    reader.frames_to_read = [(0., []), (10., [])] + [(float(second), [person]) for second in range(11,21)]
    run = finish(service, service.submit(intrusion_command(),'actor','intrusion-start'))
    assert run.state == 'completed' and run.processed_media_ms == 20000
    page = service.events('intrusion-agent','actor',{'limit':100})
    assert len(page.items) == 1 and page.items[0].event_type == 'person_intrusion'
    event = service.event('intrusion-agent',page.items[0].id,'actor')
    assert event.start_media_ms == 11000 and event.end_media_ms == 19000
    assert '连续确认 8.0 秒' in event.reason


def test_bad_decoder_is_failure_never_absence(runtime):
    service, _, reader, _ = runtime
    reader.frames_to_read = [(0., [])]
    reader.failure = True
    run = finish(service, service.submit(command(),'actor','failed-reader'))
    assert run.state == 'failed' and 'private' not in run.message
    assert service.events('agent','actor',{'limit':100}).items == []


def test_source_snapshot_and_unsupported_parameters_fail_before_start(runtime):
    service, _, _, _ = runtime
    c = command()
    c.source_snapshots[0].row_version = 2
    with pytest.raises(Error) as exc: service.submit(c,'actor','changed-source')
    assert exc.value.status == 409
    c = command()
    from app.shared.monitoring_parameters import ParameterSetting
    c.config.channels[0].parameters.append(ParameterSetting(key='require_tracking',value=True))
    with pytest.raises(Error) as exc: service.submit(c,'actor','unsupported')
    assert exc.value.status == 422
    assert service.runs('agent','actor') == []


def test_runtime_source_check_ignores_probe_versions_but_checks_real_input(runtime):
    service,sessions,_,_=runtime
    with sessions() as db:
        identity=service._source_identity(db,'video')
        source=db.get(Source,'video')
        source.row_version+=10
        source.name='Renamed without changing decoder input'
        source.status='connecting'
        db.commit()
    with sessions() as db:
        assert service._checked_source(db,command().source_snapshots[0],identity).id=='video'


def test_running_executor_survives_source_probe_version_update(runtime):
    service,sessions,reader,_=runtime
    def frames(self):
        yield 0.,[]
        with sessions() as db:
            source=db.get(Source,'video')
            source.row_version+=1
            source.observed_at='2026-10-29T00:00:00Z'
            db.commit()
        # Exercise the periodic check in _execute, not only the helper directly.
        time.sleep(2.1)
        yield 15.,[]
        yield 30.,[]
        yield 45.,[]
    reader.frames=frames
    run=finish(service,service.submit(command(),'actor','probe-during-execution'))
    assert run.state=='completed',(run.error_code,run.message)
    assert run.error_code is None
    assert len(service.events('agent','actor',{'limit':100}).items)==1


def test_verified_camera_remains_readable_during_connection_probe(runtime):
    from app.modules.sources import resolve_execution_input
    service,sessions,_,config=runtime
    class Gateway:
        def ensure_published(self,source,networks):
            assert source.id=='video'
            return 'plaza'
    with sessions() as db:
        source=db.get(Source,'video')
        source.kind='camera';source.status='connecting';source.observed_at='2026-10-29T00:00:00Z'
        db.commit()
        _,locator=resolve_execution_input(db,config,'video',Gateway())
        assert locator.endswith('/plaza')
        source.observed_at=None
        db.commit()
        with pytest.raises(Error):resolve_execution_input(db,config,'video',Gateway())


@pytest.mark.parametrize('field,value',[
    ('address','rtsp://127.0.0.1:8554/other'),('credentials','changed-secret'),
    ('width',1280),('media_key','different.mp4'),('archived',True),
])
def test_runtime_source_check_rejects_real_input_changes(runtime,field,value):
    service,sessions,_,_=runtime
    with sessions() as db:
        identity=service._source_identity(db,'video')
        setattr(db.get(Source,'video'),field,value)
        db.commit()
    with sessions() as db,pytest.raises(Error):
        service._checked_source(db,command().source_snapshots[0],identity)


def test_stop_is_durable_and_channel_conflicts_are_atomic(runtime):
    service, _, reader, _ = runtime
    def waiting(self):
        yield 0., []
        while not self.stop.wait(.02): pass
    reader.frames = waiting
    first = service.submit(command(),'actor','ongoing')
    deadline = time.monotonic()+3
    while time.monotonic()<deadline and service.operation('agent',first.id,'actor').state!='succeeded': time.sleep(.01)
    with pytest.raises(Error) as exc: service.submit(command(),'actor','conflict')
    assert exc.value.status == 409
    run = service.runs('agent','actor')[0]
    stop = RuntimeCommand(kind='stop',agent_id='agent',stop_run_id=run.id)
    op = service.submit(stop,'actor','stop')
    assert finish(service,op).state == 'stopped'
    assert service.operation('agent',op.id,'actor').state == 'succeeded'
    assert service.submit(stop,'actor','stop').id == op.id
    assert service.events('agent','actor',{'limit':100}).items == []


def test_concurrency_changes_dispatch_existing_queue_without_restart(runtime):
    from app.shared.models import Setting
    service,sessions,reader,_=runtime
    service.close()
    with sessions() as db:
        row=db.get(Setting,'resources');row.values={**row.values,'max_concurrent_jobs':1};db.commit()
    service.start()
    def frames(self):
        yield 0.,[]
        while not self.stop.wait(.02):pass
    reader.frames=frames
    def start(agent):
        request=command();request.agent_id=agent
        service.submit(request,'actor',agent)
    def state(agent):return service.runs(agent,'actor')[0].state
    start('first');start('second')
    deadline=time.monotonic()+3
    while state('first')!='running' and time.monotonic()<deadline:time.sleep(.02)
    assert state('second')=='queued'
    with sessions() as db:
        row=db.get(Setting,'resources');row.values={**row.values,'max_concurrent_jobs':2};db.commit()
    deadline=time.monotonic()+5
    while state('second')!='running' and time.monotonic()<deadline:time.sleep(.02)
    assert state('first')==state('second')=='running'
    with sessions() as db:
        row=db.get(Setting,'resources');row.values={**row.values,'max_concurrent_jobs':1};db.commit()
    start('third');time.sleep(.1)
    assert state('third')=='queued'
    assert state('first')==state('second')=='running'


def test_delete_running_task_stops_inference_and_cleans_only_owned_records(runtime):
    from app.modules.agents import workflow
    from app.modules.agents.models import Agent,AgentRevision
    from app.modules.agent_templates.models import AgentTemplate,AgentTemplateRevision,TemplateTaskLink
    from app.modules.local_execution.models import LocalRun,LocalEvent,LocalOperation
    service,sessions,reader,config=runtime
    def frames(self):
        yield 0.,[]
        while not self.stop.wait(.02):pass
    reader.frames=frames
    service.submit(command(),'actor','deletable')
    deadline=time.monotonic()+3
    while service.runs('agent','actor')[0].state!='running' and time.monotonic()<deadline:time.sleep(.02)
    rid=service.runs('agent','actor')[0].id
    evidence=config.var_root/'media/local-evidence/delete-test.jpg'
    evidence.parent.mkdir(parents=True,exist_ok=True);evidence.write_bytes(b'test evidence')
    with sessions() as db:
        db.add(Agent(id='agent',name='delete me',description='',owner_id='actor'));db.flush()
        db.add(AgentRevision(id='revision',agent_id='agent',revision_no=1,state='published',config=command().config.model_dump(mode='json')))
        db.add(AgentTemplate(id='template',name='keep template',description=''));db.flush()
        db.add(AgentTemplateRevision(id='template-revision',template_id='template',revision_no=1,state='published',config={}));db.flush()
        db.add(TemplateTaskLink(agent_id='agent',template_id='template',template_revision_id='template-revision'))
        db.add(LocalEvent(id='delete-event',agent_id='agent',actor_id='actor',run_id=rid,payload={},evidence_key='local-evidence/delete-test.jpg'))
        db.commit()
    with sessions() as db:workflow.delete_task(db,service,'agent',1,'actor')
    assert service.futures.get(rid) is None
    assert not evidence.exists()
    with sessions() as db:
        assert db.get(Agent,'agent') is None
        assert db.get(AgentRevision,'revision') is None
        assert db.get(TemplateTaskLink,'agent') is None
        assert db.get(AgentTemplate,'template') is not None
        assert db.get(Source,'video') is not None
        assert db.get(LocalRun,rid) is None
        assert db.get(LocalEvent,1) is None
        assert not db.query(LocalOperation).filter(LocalOperation.agent_id=='agent').count()
    assert (config.var_root/'media/sample.mp4').exists()


def test_archiving_blocks_future_execution_and_actor_scope(runtime):
    service, _, _, _ = runtime
    service.set_archived('agent',True,'actor')
    with pytest.raises(Error) as exc: service.submit(command(),'actor','archived')
    assert exc.value.status == 409
    service.set_archived('agent',False,'actor')
    finish(service,service.submit(command(),'actor','good'))
    assert service.runs('agent','other-actor') == []
    assert service.events('agent','other-actor',{'limit':100}).items == []


def test_shutdown_and_interrupted_process_recovery_never_report_running(runtime):
    service, sessions, _, config = runtime
    from app.modules.local_execution.models import LocalRun
    c = command()
    from app.modules.agents.contracts import RunDTO
    payload = RunDTO(id='abandoned',agent_id='agent',revision_id='revision',revision_no=1,channel_id='channel',
        channel_name='岗位',source_id='video',state='running',source_kind='file',config_snapshot=c.config).model_dump(mode='json')
    service.close()
    with sessions() as db:
        db.add(LocalRun(id='abandoned',agent_id='agent',actor_id='actor',channel_id='channel',source_id='video',state='running',payload=payload,observation={}))
        db.commit()
    second = LocalAgentServices(config,sessions,Adapter(),detector_factory=Detector,reader_factory=Reader)
    second.start()
    try:
        run = second.runs('agent','actor')[0]
        assert run.state == 'failed' and run.error_code == 'executor_interrupted'
    finally: second.close()


def test_shutdown_keeps_process_lock_until_blocked_inference_really_exits(runtime):
    service, sessions, reader, config = runtime
    entered, release = Event(), Event()
    class BlockingDetector:
        def __init__(self,*args,**kwargs): pass
        def detect(self,frame):
            entered.set()
            release.wait(15)
            return []
    service.detector_factory = BlockingDetector
    reader.frames_to_read = [(0., [])]
    service.submit(command(),'actor','blocked')
    assert entered.wait(3)
    service.close()
    replacement = LocalAgentServices(config,sessions,Adapter(),detector_factory=Detector,reader_factory=Reader)
    with pytest.raises(Error) as exc:
        replacement.start()
    assert exc.value.code == 'executor_already_running'
    assert service.runs('agent','actor')[0].state == 'stopping'
    release.set()
    deadline = time.monotonic()+5
    while time.monotonic()<deadline:
        try:
            replacement.start()
            break
        except Error as error:
            assert error.code == 'executor_already_running'
            time.sleep(.02)
    else: pytest.fail('executor ownership lock was not released after worker exit')
    replacement.close()


def test_stream_cursor_never_skips_event_inserted_between_snapshot_queries(runtime):
    service, sessions, _, config = runtime
    finish(service,service.submit(command(),'actor','seed-event'))
    first_event = service.events('agent','actor',{'limit':100}).items[0]
    engine = sessions.kw['bind']
    from sqlalchemy import event as sqlalchemy_event
    selects = 0
    inserted = False
    second = dict(service.event('agent',first_event.id,'actor').model_dump(mode='json'))
    second.update(id='concurrent-event',occurred_at='2099-01-01T00:00:00Z',updated_at='2099-01-01T00:00:00Z')
    def inject(_connection,_cursor,statement,_parameters,_context,_many):
        nonlocal selects,inserted
        if statement.lstrip().upper().startswith('SELECT') and 'local_events' in statement.lower():
            selects += 1
            if selects == 2 and not inserted:
                inserted = True
                with sqlite3.connect(config.var_root/'vision.db') as external:
                    external.execute('INSERT INTO local_events (id,agent_id,actor_id,run_id,payload,evidence_key) VALUES (?,?,?,?,?,NULL)',
                        ('concurrent-event','agent','actor',second['run_id'],json.dumps(second)))
    sqlalchemy_event.listen(engine,'before_cursor_execute',inject)
    try:
        page = service.events('agent','actor',{'limit':100})
    finally:
        sqlalchemy_event.remove(engine,'before_cursor_execute',inject)
    assert inserted
    assert 'concurrent-event' not in {item.id for item in page.items}
    later = service.events('agent','actor',{'limit':100},after=page.stream_cursor)
    assert [item.id for item in later.items] == ['concurrent-event']


