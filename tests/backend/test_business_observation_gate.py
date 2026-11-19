"""Business events are published only by a closed, compatible observation window."""
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
from app.modules.local_execution.intrusion import IntrusionRule
from app.modules.local_execution.models import LocalEvent, LocalRun
from app.modules.local_execution.presence import PresenceRule
from app.modules.local_execution.service import LocalAgentServices
from app.modules.semantics.models import ObservationRecord

ROI = [(0, 0), (1, 0), (1, 1), (0, 1)]
PERSON = {'label': 'person', 'x': .3, 'y': .3, 'width': .2, 'height': .5,
          'confidence': .9}


def textured():
    return np.random.default_rng(7).integers(0, 255, (48, 64, 3), dtype=np.uint8)


def saturated():
    return np.full((48, 64, 3), 255, dtype=np.uint8)


class Adapter:
    def is_ready(self): return True
    def resolve_model(self, reference): return Path('trusted.onnx')
    def deployments(self): return []


class Detector:
    detections = []

    def __init__(self, path, confidence=.5): pass

    def detect(self, frame):
        return list(self.detections.pop(0))


class Reader:
    samples = []
    stop_after = None

    def __init__(self, *args, **kwargs): self.stop = kwargs['stop']
    def __enter__(self): return self
    def __exit__(self, *args): pass

    def frames(self):
        for timestamp, frame in self.samples:
            if self.stop.is_set(): return
            yield timestamp, frame
            if self.stop_after == timestamp:
                self.stop.set()
                return


@pytest.fixture
def runtime(tmp_path):
    config = Config(var_root=tmp_path, agent_demo=False, observation_window_seconds=5.0)
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
    service = LocalAgentServices(config, sessions, Adapter(), detector_factory=Detector,
                                 reader_factory=Reader)
    service.start()
    yield service, sessions, config
    service.close()
    engine.dispose()


def command(*, rule='absence', duration=2, end=5000, alarm_interval=60):
    parameters = [dict(key='sample_interval_seconds', value=1),
                  dict(key='confidence_threshold', value=.5)]
    if rule == 'absence':
        parameters.append(dict(key='alarm_interval_seconds', value=alarm_interval))
    else:
        parameters.extend([dict(key='tracking_timeout_seconds', value=2),
                           dict(key='exit_confirmation_seconds', value=3)])
    config = RevisionConfig(channels=[dict(channel_id='channel', name='岗位', target='person',
        rule=rule, duration_seconds=duration,
        sources=[dict(source_id='video', start_media_ms=0, end_media_ms=end,
                      regions=[dict(id='roi', points=ROI)])],
        capability_ref=dict(model_id='model', model_version='1', template_id='template',
                            template_version='1'), parameters=parameters)])
    return RuntimeCommand(kind='start', agent_id='agent', revision_id='revision', revision_no=1,
                          config=config, channel_ids=['channel'], source_kinds={'video': 'file'},
                          source_snapshots=[SourceSnapshot(id='video', row_version=1, kind='file',
                                                           sha256='abc', width=64, height=48,
                                                           duration_ms=60000)])


def sequence(last, *, invalid=(), people=()):
    Reader.samples = [(float(timestamp), saturated() if timestamp in invalid else textured())
                      for timestamp in range(last + 1)]
    Detector.detections = [[PERSON] if timestamp in people else []
                           for timestamp in range(last + 1)]
    Reader.stop_after = None


def finish(service, operation):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        runs = service.runs('agent', 'actor')
        if runs and all(run.state not in {'queued', 'starting', 'running', 'stopping',
                                          'reconnecting'} for run in runs):
            return runs[0]
        time.sleep(.01)
    pytest.fail('executor failed to settle')


def events(sessions):
    with sessions() as db:
        rows = list(db.scalars(select(LocalEvent).order_by(LocalEvent.sequence)))
        return [row.payload for row in rows]


def observations(sessions):
    with sessions() as db:
        return list(db.scalars(select(ObservationRecord).order_by(ObservationRecord.sequence)))


def capture_rule(monkeypatch, rule_type):
    instances = []
    original = rule_type.mark_unavailable
    def capture(rule):
        if rule not in instances:
            instances.append(rule)
        return original(rule)
    monkeypatch.setattr(rule_type, 'mark_unavailable', capture)
    return instances


def test_disabling_observation_records_does_not_bypass_the_business_gate(runtime):
    service, sessions, config = runtime
    config.observation_records = False
    sequence(2)
    run = finish(service, service.submit(command(end=2000), 'actor', 'records-disabled'))
    assert run.state == 'completed'
    assert events(sessions) == []
    assert observations(sessions) == []


def test_invalid_intrusion_window_discards_alarm_and_resets_arm_clear_state(runtime, monkeypatch):
    service, sessions, config = runtime
    config.observation_window_seconds = 10.0
    rules = capture_rule(monkeypatch, IntrusionRule)
    Reader.samples = [(float(timestamp), saturated()) for timestamp in range(21)]
    Detector.detections = [[] if timestamp <= 10 else [PERSON] for timestamp in range(21)]
    Reader.stop_after = None
    run = finish(service, service.submit(
        command(rule='intrusion', duration=2, end=20000), 'actor', 'invalid-intrusion'))
    assert run.state == 'completed'
    assert events(sessions) == []
    rule, = rules
    assert rule.waiting_clear is True
    assert rule.alarmed is False
    assert rule.clear_since is None
    assert rule.candidates == {}
    assert rule.last_timestamp is None


def test_valid_intrusion_publishes_with_trigger_time_and_run_revision(runtime):
    service, sessions, config = runtime
    config.observation_window_seconds = 10.0
    sequence(20, people=range(11, 21))
    run = finish(service, service.submit(
        command(rule='intrusion', duration=2, end=20000), 'actor', 'valid-intrusion'))
    assert run.state == 'completed'
    stored_events = events(sessions)
    assert [event['event_type'] for event in stored_events] == ['person_intrusion']
    assert stored_events[0]['end_media_ms'] == 13000
    assert stored_events[0]['revision_id'] == 'revision'
    assert stored_events[0]['run_id'] == run.id
    stored = observations(sessions)
    assert stored[-1].verdict == 'detected'
    assert stored[-1].window_end == 20
    assert stored[-1].route_version == 'local-r1'
    assert stored[-1].model_version == '1'


def test_invalid_second_does_not_join_absence_timing_across_windows(runtime, monkeypatch):
    service, sessions, _ = runtime
    rules = capture_rule(monkeypatch, PresenceRule)
    sequence(22, invalid={11})
    run = finish(service, service.submit(
        command(duration=11, end=22000), 'actor', 'segmented-absence'))
    assert run.state == 'completed'
    assert events(sessions) == []
    rule, = rules
    assert rule.absent_since == 16


def test_valid_absence_and_recovery_publish_once_with_actual_trigger_windows(runtime):
    service, sessions, _ = runtime
    sequence(10, people=range(6, 11))
    run = finish(service, service.submit(command(end=10000), 'actor', 'valid-recovery'))
    assert run.state == 'completed'
    stored_events = events(sessions)
    assert [event['event_type'] for event in stored_events] == [
        'person_absence', 'person_presence_restored']
    assert [event['end_media_ms'] for event in stored_events] == [2000, 8000]
    assert {event['revision_id'] for event in stored_events} == {'revision'}
    assert [item.verdict for item in observations(sessions)] == ['not_detected', 'detected']
    with sessions() as db:
        row = db.get(LocalRun, run.id)
    assert row.payload['alert_state'] == 'normal'
    assert row.payload['alert_started_at'] is None


def test_insufficient_window_drops_pending_recovery(runtime):
    service, sessions, _ = runtime
    Reader.samples = [(float(timestamp), textured() if timestamp <= 5 else saturated())
                      for timestamp in range(11)]
    Detector.detections = [[] if timestamp <= 5 else [PERSON] for timestamp in range(11)]
    Reader.stop_after = None
    run = finish(service, service.submit(command(end=10000), 'actor', 'invalid-recovery'))
    assert run.state == 'completed'
    assert [event['event_type'] for event in events(sessions)] == ['person_absence']
    with sessions() as db:
        row = db.get(LocalRun, run.id)
    assert row.payload['alert_state'] == 'absence'


def test_valid_person_window_recovers_after_an_invalid_recovery_window(runtime):
    service, sessions, _ = runtime
    Reader.samples = [(float(timestamp), textured() if timestamp <= 5 or timestamp >= 11 else saturated())
                      for timestamp in range(16)]
    Detector.detections = [[] if timestamp <= 5 else [PERSON] for timestamp in range(16)]
    Reader.stop_after = None
    run = finish(service, service.submit(command(end=15000), 'actor', 'retry-recovery'))
    assert run.state == 'completed'
    stored_events = events(sessions)
    assert [event['event_type'] for event in stored_events] == [
        'person_absence', 'person_presence_restored']
    assert [event['end_media_ms'] for event in stored_events] == [2000, 13000]
    with sessions() as db:
        row = db.get(LocalRun, run.id)
    assert row.payload['alert_state'] == 'normal'


def test_valid_absence_restarts_after_an_invalid_initial_transition(runtime):
    service, sessions, _ = runtime
    Reader.samples = [(float(timestamp), saturated() if timestamp <= 5 else textured())
                      for timestamp in range(11)]
    Detector.detections = [[] for _ in range(11)]
    Reader.stop_after = None
    run = finish(service, service.submit(command(end=10000), 'actor', 'retry-absence'))
    assert run.state == 'completed'
    stored_events = events(sessions)
    assert [event['event_type'] for event in stored_events] == ['person_absence']
    assert stored_events[0]['end_media_ms'] == 8000
    with sessions() as db:
        row = db.get(LocalRun, run.id)
    assert row.payload['alert_state'] == 'absence'


def test_detected_window_drops_absence_and_restarts_the_next_empty_window(runtime):
    service, sessions, _ = runtime
    sequence(10, people={3, 4})
    run = finish(service, service.submit(command(end=10000), 'actor', 'mixed-window'))
    assert run.state == 'completed'
    stored_events = events(sessions)
    assert [event['event_type'] for event in stored_events] == ['person_absence']
    assert stored_events[0]['end_media_ms'] == 8000
    with sessions() as db:
        row = db.get(LocalRun, run.id)
    assert row.payload['alert_state'] == 'absence'


def test_multiple_transitions_in_one_window_are_atomic_and_restart_absence(runtime):
    service, sessions, config = runtime
    config.observation_window_seconds = 10.0
    sequence(20, people={2, 3})
    run = finish(service, service.submit(
        command(duration=1, end=20000), 'actor', 'multiple-transitions'))
    assert run.state == 'completed'
    stored_events = events(sessions)
    assert [event['event_type'] for event in stored_events] == ['person_absence']
    assert stored_events[0]['end_media_ms'] == 12000
    with sessions() as db:
        row = db.get(LocalRun, run.id)
    assert row.payload['alert_state'] == 'absence'


def test_valid_absence_repeats_without_window_queue_duplicates(runtime):
    service, sessions, _ = runtime
    sequence(10)
    run = finish(service, service.submit(
        command(end=10000, alarm_interval=2), 'actor', 'repeat-absence'))
    assert run.state == 'completed'
    stored_events = events(sessions)
    assert [event['event_type'] for event in stored_events] == ['person_absence'] * 5
    assert [event['end_media_ms'] for event in stored_events] == [2000, 4000, 6000, 8000, 10000]


def test_file_completion_before_window_close_discards_pending_event(runtime):
    service, sessions, config = runtime
    config.observation_window_seconds = 10.0
    sequence(2)
    run = finish(service, service.submit(command(end=2000), 'actor', 'short-file'))
    assert run.state == 'completed'
    assert events(sessions) == []
    assert not list((config.var_root / 'media').glob('local-evidence/**/*.jpg'))


def test_stop_before_window_close_discards_pending_event_and_evidence(runtime):
    service, sessions, config = runtime
    config.observation_window_seconds = 10.0
    sequence(2)
    Reader.stop_after = 2.0
    run = finish(service, service.submit(command(end=10000), 'actor', 'stop-pending'))
    assert run.state == 'stopped'
    assert events(sessions) == []
    assert not list((config.var_root / 'media').glob('local-evidence/**/*.jpg'))
