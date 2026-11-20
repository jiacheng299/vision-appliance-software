"""执行器观察门控：只有已关闭且结论兼容的窗口才能发布业务事件。"""
import time
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import select

from app.shared.config import Config
from app.shared.db import make_engine, migrate, session_factory
from app.shared.models import Source
from app.modules.agents.contracts import RunDTO, RuntimeCommand, SourceSnapshot
from app.modules.agents.models import Agent
from app.modules.agents.schemas import CapabilityRef, RevisionConfig, channel_sources
from app.modules.local_execution.models import LocalEvent, LocalRun
from app.modules.local_execution.service import LocalAgentServices
from app.modules.local_execution.shadow_runtime import ShadowRuntime
from app.modules.routing.models import RouteState
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


def make_runtime(tmp_path, **overrides):
    config = Config(var_root=tmp_path, agent_demo=False, observation_window_seconds=10.0,
                    **overrides)
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
    return service, sessions, engine


@pytest.fixture
def runtime(tmp_path):
    service, sessions, engine = make_runtime(tmp_path)
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


def test_clean_window_records_not_detected_and_publishes_absence(runtime):
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
    with sessions() as db:
        events = list(db.scalars(select(LocalEvent)))
    assert events == []


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
    assert events == []


def test_disabling_the_feature_writes_nothing(tmp_path):
    config = Config(var_root=tmp_path, agent_demo=False, observation_records=False)
    assert config.observation_records is False
    assert config.observation_window_seconds == 30.0


PERSON_BOX = {'label': 'person', 'x': .3, 'y': .3, 'width': .2, 'height': .5,
              'confidence': .9}


def seed_candidate(sessions, members=('candidate-a',)):
    with sessions() as db:
        row = db.query(RouteState).filter_by(agent_id='agent', channel_id='channel',
                                             source_id='video').one_or_none()
        if row is None:
            row = RouteState(id='route', actor_id='actor', agent_id='agent', channel_id='channel',
                             source_id='video', rule='absence', active_members=['active-person'],
                             active_version='route-v7', active_since=time.time(), mode='candidate',
                             candidate_members=list(members))
            db.add(row)
        else:
            row.candidate_members = list(members)
            row.mode = 'candidate'
        db.commit()


def candidate_reference(db, member, channel):
    return CapabilityRef(model_id=member, model_version='candidate-v1',
                         template_id='candidate-template', template_version='1')


class CandidateAdapter(Adapter):
    def resolve_model(self, reference):
        if reference.model_id == 'model':
            return Path('trusted.onnx')
        if reference.model_id in {'candidate-a', 'candidate-b'}:
            return Path('shared.onnx')
        if reference.model_id == 'broken-candidate':
            return Path('broken.onnx')
        return Path(f'{reference.model_id}.onnx')


class SplitDetector:
    loads = []
    active_boxes = [PERSON_BOX]

    def __init__(self, path, confidence=.5):
        self.path = str(path)
        type(self).loads.append(self.path)

    def detect(self, frame):
        if self.path == 'trusted.onnx':
            return [dict(box) for box in self.active_boxes]
        if self.path == 'broken.onnx':
            raise RuntimeError('candidate inference failed')
        return []


def prepare_split_runtime(service):
    SplitDetector.loads = []
    SplitDetector.active_boxes = [PERSON_BOX]
    service.model_adapter = CandidateAdapter()
    service.detector_factory = SplitDetector
    service.candidate_resolver = candidate_reference


def test_candidate_runs_on_the_same_frames_without_publishing_business_results(runtime):
    service, sessions = runtime
    prepare_split_runtime(service)
    seed_candidate(sessions)
    run = finish(service, service.submit(command(), 'actor', 'candidate-shadow'))
    assert run.state == 'completed'
    stored = records(sessions)
    active = [item for item in stored if item.route_role == 'active']
    candidate = [item for item in stored if item.route_role == 'candidate']
    assert len(active) == len(candidate) == 3
    assert [item.verdict for item in active] == ['detected'] * 3
    assert [item.verdict for item in candidate] == ['not_detected'] * 3
    assert [item.window_end for item in candidate] == [item.window_end for item in active]
    assert all(item.route_version == 'route-v7' for item in active)
    assert all(item.route_version.startswith('route-v7+candidate-') for item in candidate)
    assert all(item.model_version == 'candidate-v1' for item in candidate)
    with sessions() as db:
        assert list(db.scalars(select(LocalEvent))) == []
        row = db.query(LocalRun).one()
        assert row.observation['count'] == 1
        assert row.observation['observed_at']


def direct_shadow(service, sessions):
    request = command()
    channel = request.config.channels[0]
    run = RunDTO(id='direct-shadow', agent_id='agent', revision_id='revision', revision_no=1,
                 channel_id='channel', channel_name='岗位', source_id='video', state='running',
                 source_kind='file', config_snapshot=request.config,
                 source_snapshot=request.source_snapshots[0])
    return ShadowRuntime(service.config, sessions, service.model_adapter, run=run,
                         channel=channel, binding=channel_sources(channel)[0],
                         parameters=service._parameters(channel), actor_id='actor',
                         detector_factory=SplitDetector, candidate_resolver=candidate_reference,
                         close_window=service._close_observation_window,
                         reset_rule=service._reset_window_rule,
                         sample_evidence=service._sample_evidence)


def test_candidate_detector_cache_survives_candidate_changes_and_reconnect(runtime):
    service, sessions = runtime
    prepare_split_runtime(service)
    seed_candidate(sessions)
    shadow = direct_shadow(service, sessions)
    frame = textured()
    for timestamp in (0.0, 10.0, 11.0):
        shadow.observe(timestamp, frame)
    seed_candidate(sessions, ('candidate-b',))
    for timestamp in (12.0, 22.0, 23.0):
        shadow.observe(timestamp, frame)
    shadow.reset_observation()
    for timestamp in (24.0, 34.0):
        shadow.observe(timestamp, frame)
    seed_candidate(sessions, ('candidate-c',))
    for timestamp in (35.0, 45.0):
        shadow.observe(timestamp, frame)
    seed_candidate(sessions, ('candidate-a',))
    for timestamp in (46.0, 56.0):
        shadow.observe(timestamp, frame)
    assert SplitDetector.loads == ['shared.onnx', 'candidate-c.onnx']
    stored = [item for item in records(sessions) if item.route_role == 'candidate']
    assert [item.window_start for item in stored] == [0.0, 12.0, 24.0, 35.0, 46.0]
    with sessions() as db:
        row = db.query(RouteState).one()
        assert row.active_version == 'route-v7'
        assert row.active_members == ['active-person']
        assert row.valid_windows == 0


def test_uninstalled_candidate_is_unavailable_without_borrowing_active_detector(runtime):
    service, sessions = runtime
    Detector.boxes = []
    seed_candidate(sessions, ('yolo11s-person',))
    run = finish(service, service.submit(command(), 'actor', 'candidate-not-installed'))
    assert run.state == 'completed'
    stored = records(sessions)
    assert stored and all(item.route_role == 'active' for item in stored)
    with sessions() as db:
        events = list(db.scalars(select(LocalEvent)))
    assert [event.payload['event_type'] for event in events] == ['person_absence']


def test_candidate_inference_failure_does_not_affect_active_observation_or_event(runtime):
    service, sessions = runtime
    prepare_split_runtime(service)
    SplitDetector.active_boxes = []
    seed_candidate(sessions, ('broken-candidate',))
    run = finish(service, service.submit(command(), 'actor', 'candidate-inference-failure'))
    assert run.state == 'completed'
    stored = records(sessions)
    assert stored and all(item.route_role == 'active' for item in stored)
    with sessions() as db:
        events = list(db.scalars(select(LocalEvent)))
        row = db.query(LocalRun).one()
        assert row.observation['count'] == 0
    assert [event.payload['event_type'] for event in events] == ['person_absence']
