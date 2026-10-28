"""Real executor lifecycle contract; injectable decoder/detector keep unit tests offline."""
import time
from pathlib import Path
from threading import Event

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


def command():
    config = RevisionConfig(channels=[dict(channel_id='channel', name='岗位', target='person', rule='absence',
        duration_seconds=30, sources=[dict(source_id='video', start_media_ms=0, end_media_ms=60000,
        regions=[dict(id='roi', points=[(0,0),(1,0),(1,1),(0,1)])])],
        capability_ref=dict(model_id='model',model_version='1',template_id='template',template_version='1'),
        parameters=[dict(key='sample_interval_seconds',value=15),dict(key='confidence_threshold',value=.5)])])
    return RuntimeCommand(kind='start',agent_id='agent',revision_id='revision',revision_no=1,config=config,
        channel_ids=['channel'],source_kinds={'video':'file'},
        source_snapshots=[SourceSnapshot(id='video',row_version=1,kind='file',sha256='abc',width=640,height=480,duration_ms=60000)])


def finish(service, operation):
    deadline = time.monotonic()+5
    while time.monotonic() < deadline:
        runs = service.runs('agent','actor')
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


