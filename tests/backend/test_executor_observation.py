"""执行器影子接入：窗口结束时写观察记录，但报警行为完全不变。"""
import time
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import select

from app.shared.config import Config
from app.shared.db import make_engine, migrate, session_factory
from app.shared.models import Source
from app.modules.agents.contracts import RuntimeCommand, SourceSnapshot
from app.modules.agents.models import Agent
from app.modules.agents.schemas import RevisionConfig
from app.modules.local_execution.models import LocalEvent
from app.modules.local_execution.service import LocalAgentServices
from app.modules.semantics.models import ObservationRecord

ROI = [(0, 0), (1, 0), (1, 1), (0, 1)]


class Adapter:
    def is_ready(self): return True
    def resolve_model(self, reference): return Path('trusted.onnx')
    def deployments(self): return []


class Detector:
    boxes = []
    def __init__(self, path, confidence=.5): pass
    def detect(self, frame): return list(self.boxes)


class Reader:
    timestamps = [float(index) for index in range(31)]
    frame = None
    def __init__(self, *args, **kwargs): self.stop = kwargs['stop']
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def frames(self):
        for timestamp in self.timestamps:
            if self.stop.is_set(): return
            yield timestamp, self.frame


def textured():
    """A detailed frame so sharpness is genuinely measurable."""
    return np.random.default_rng(7).integers(0, 255, (48, 64, 3), dtype=np.uint8)


def saturated():
    return np.full((48, 64, 3), 255, dtype=np.uint8)


@pytest.fixture
def runtime(tmp_path):
    config = Config(var_root=tmp_path, agent_demo=False, observation_window_seconds=10.0)
    config.prepare()
    engine = make_engine(config)
    migrate(engine)
    sessions = session_factory(engine)
    from app.modules import settings
    with sessions() as db:
        settings.initialize(db)
        db.add(Source(id='video', name='录像', kind='file', status='ready', width=64, height=48,
                      duration_ms=60000, sha256='abc', media_key='sample.mp4'))
        db.add(Agent(id='agent', name='任务', description='', owner_id='actor'))
        db.commit()
    (tmp_path / 'media' / 'sample.mp4').write_bytes(b'controlled fixture')
    Reader.frame = textured()
    Detector.boxes = []
    service = LocalAgentServices(config, sessions, Adapter(), detector_factory=Detector,
                                 reader_factory=Reader)
    service.start()
    yield service, sessions
    service.close()
    engine.dispose()


def command():
    config = RevisionConfig(channels=[dict(channel_id='channel', name='岗位', target='person',
        rule='absence', duration_seconds=12,
        sources=[dict(source_id='video', start_media_ms=0, end_media_ms=30000,
                      regions=[dict(id='roi', points=ROI)])],
        capability_ref=dict(model_id='model', model_version='1', template_id='template',
                            template_version='1'),
        parameters=[dict(key='sample_interval_seconds', value=1),
                    dict(key='confidence_threshold', value=.5),
                    dict(key='alarm_interval_seconds', value=60)])])
    return RuntimeCommand(kind='start', agent_id='agent', revision_id='revision', revision_no=1,
                          config=config, channel_ids=['channel'], source_kinds={'video': 'file'},
                          source_snapshots=[SourceSnapshot(id='video', row_version=1, kind='file',
                                                           sha256='abc', width=64, height=48,
                                                           duration_ms=60000)])


def finish(service, operation):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        runs = service.runs('agent', 'actor')
        if runs and all(run.state not in {'queued', 'starting', 'running', 'stopping',
                                          'reconnecting'} for run in runs):
            return runs[0]
        time.sleep(.01)
    pytest.fail('executor failed to settle')


def records(sessions):
    with sessions() as db:
        return list(db.scalars(select(ObservationRecord).order_by(ObservationRecord.sequence)))


def test_clean_window_records_not_detected_and_keeps_alarms_unchanged(runtime):
    service, sessions = runtime
    run = finish(service, service.submit(command(), 'actor', 'observation-clean'))
    assert run.state == 'completed'
    stored = records(sessions)
    assert stored, 'closed windows must produce observation records'
    assert all(item.verdict == 'not_detected' for item in stored)
    assert all(item.task_key == 'person/absence' for item in stored)
    assert all(item.route_version == 'local-r1' for item in stored)
    assert all(item.gates for item in stored)
    # Twelve seconds of continuous absence still raises its alarm exactly as before.
    with sessions() as db:
        events = list(db.scalars(select(LocalEvent)))
    assert [event.payload['event_type'] for event in events] == ['person_absence']


def test_detection_inside_the_window_is_recorded_as_detected(runtime):
    service, sessions = runtime
    Detector.boxes = [{'label': 'person', 'x': .3, 'y': .3, 'width': .2, 'height': .5,
                       'confidence': .9}]
    run = finish(service, service.submit(command(), 'actor', 'observation-hit'))
    assert run.state == 'completed'
    stored = records(sessions)
    assert stored and all(item.verdict == 'detected' for item in stored)
    assert stored[0].detection_count >= 1
    assert stored[0].metrics['target_scale_px'] > 0


def test_saturated_frames_cannot_be_claimed_as_absence(runtime):
    service, sessions = runtime
    Reader.frame = saturated()
    run = finish(service, service.submit(command(), 'actor', 'observation-glare'))
    assert run.state == 'completed'
    stored = records(sessions)
    assert stored and all(item.verdict == 'insufficient' for item in stored)
    assert any('过曝' in reason for item in stored for reason in item.reasons)
    # The alarm logic is untouched: glare still means "no person counted", as before.
    with sessions() as db:
        events = list(db.scalars(select(LocalEvent)))
    assert [event.payload['event_type'] for event in events] == ['person_absence']


def test_observation_failure_never_breaks_monitoring(runtime, monkeypatch):
    service, sessions = runtime
    from app.modules.semantics import service as semantics
    def explode(*args, **kwargs):
        raise RuntimeError('storage unavailable')
    monkeypatch.setattr(semantics, 'record_observation', explode)
    run = finish(service, service.submit(command(), 'actor', 'observation-broken'))
    assert run.state == 'completed'
    assert records(sessions) == []
    with sessions() as db:
        events = list(db.scalars(select(LocalEvent)))
    assert [event.payload['event_type'] for event in events] == ['person_absence']


def test_disabling_the_feature_writes_nothing(tmp_path):
    config = Config(var_root=tmp_path, agent_demo=False, observation_records=False)
    assert config.observation_records is False
    assert config.observation_window_seconds == 30.0
