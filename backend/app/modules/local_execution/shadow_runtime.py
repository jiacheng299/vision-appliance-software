"""Online candidate inference that persists observations without taking over business results."""
from dataclasses import dataclass
import logging
from pathlib import Path

from sqlalchemy import select, text

from ...shared.errors import Error
from ..agents.schemas import CapabilityRef
from ..models.models import ModelPair
from ..routing import state as route_state
from ..routing.models import RouteState
from ..semantics import service as semantics
from ..semantics.window import ObservationWindow
from .intrusion import IntrusionRule
from .presence import PresenceRule


def directory_candidate_reference(db, member, channel):
    pair = db.scalars(select(ModelPair).where(ModelPair.model_id == member,
                                              ModelPair.validation == 'passed',
                                              ModelPair.status == 'available',
                                              ModelPair.data_origin == 'real')
                      .order_by(ModelPair.created_at.desc(), ModelPair.version.desc())).first()
    if pair is None:
        raise Error(503, 'candidate_model_unavailable',
                    f'候选成员 {member} 在模型目录中没有已校验可用的真实产物，影子运行已跳过。')
    return CapabilityRef(model_id=pair.model_id, model_version=pair.version,
                         template_id=pair.template_id, template_version=pair.template_version)


@dataclass
class _CandidateContext:
    candidate: object
    detector: object
    rule: object
    window: ObservationWindow
    thresholds: object
    profile_version: int | None
    model_version: str
    window_rule_state: str | None


class ShadowRuntime:
    def __init__(self, config, sessions, model_adapter, *, run, channel, binding, parameters,
                 actor_id, detector_factory, candidate_resolver=None, close_window, reset_rule,
                 sample_evidence):
        self.config, self.sessions = config, sessions
        self.model_adapter = model_adapter
        self.run, self.channel, self.binding = run, channel, binding
        self.parameters, self.actor_id = parameters, actor_id
        self.detector_factory = detector_factory
        self.candidate_resolver = candidate_resolver or directory_candidate_reference
        self.close_window, self.reset_rule = close_window, reset_rule
        self.sample_evidence = sample_evidence
        self._detectors = {}
        self._context = None
        self._unavailable_version = None

    def reset_observation(self):
        self._context = None
        self._unavailable_version = None

    def _pending_candidate(self):
        with self.sessions() as db:
            row = db.scalars(select(RouteState).where(RouteState.agent_id == self.run.agent_id,
                                                      RouteState.actor_id == self.actor_id,
                                                      RouteState.channel_id == self.run.channel_id,
                                                      RouteState.source_id == self.run.source_id)).first()
            return route_state.pending_candidate(row) if row is not None else None

    def _rule(self):
        interval = self.parameters['sample_interval_seconds']
        regions = [region.points for region in self.binding.regions]
        if self.channel.rule == 'absence':
            return PresenceRule(regions, min_count=self.parameters['min_count'],
                                duration_seconds=self.parameters['duration_seconds'],
                                alarm_interval_seconds=self.parameters['alarm_interval_seconds'],
                                max_gap_seconds=max(3, interval * 1.5))
        return IntrusionRule(regions, entry_seconds=self.parameters['duration_seconds'],
                             occlusion_seconds=self.parameters['tracking_timeout_seconds'],
                             exit_seconds=self.parameters['exit_confirmation_seconds'],
                             max_gap_seconds=min(self.parameters['tracking_timeout_seconds'],
                                                 max(1.5, interval * 1.5)),
                             policy_name=self.config.tracker_policy)

    def _detector(self, candidate):
        references = []
        with self.sessions() as db:
            for member in candidate.members:
                if member in {'heuristic-tracker', 'zone-rule'}:
                    continue
                reference = self.candidate_resolver(db, member, self.channel)
                if reference is not None:
                    references.append(reference)
        if len(references) != 1:
            raise Error(503, 'candidate_runtime_unsupported',
                        '候选组合必须解析为一个真实检测产物，影子运行已跳过。')
        reference = references[0]
        path = self.model_adapter.resolve_model(reference)
        key = str(Path(path).resolve())
        detector = self._detectors.get(key)
        if detector is None:
            detector = self.detector_factory(path, confidence=self.parameters['confidence'])
            self._detectors[key] = detector
        return detector, reference.model_version

    def _start(self, candidate):
        self._context = None
        detector, model_version = self._detector(candidate)
        rule = self._rule()
        window_seconds = self.config.observation_window_seconds
        gate_gap = rule.max_gap if isinstance(rule, PresenceRule) else rule.max_gap_seconds
        thresholds = semantics.thresholds_for(window_seconds=window_seconds,
                                              max_gap_seconds=gate_gap)
        with self.sessions() as db:
            profile_version = semantics.profile_version_for(db, self.run.source_id)
        self._context = _CandidateContext(
            candidate=candidate, detector=detector, rule=rule,
            window=ObservationWindow(window_seconds), thresholds=thresholds,
            profile_version=profile_version, model_version=model_version,
            window_rule_state=rule.state if isinstance(rule, PresenceRule) else None)

    def _unavailable(self, candidate, error):
        self._context = None
        self._unavailable_version = candidate.version if candidate is not None else None
        logging.getLogger(__name__).warning(
            'Candidate shadow unavailable run=%s version=%s: %s',
            self.run.id, candidate.version if candidate is not None else 'sync', error)

    def observe(self, timestamp, frame, *, process_rule=True):
        try:
            candidate = self._pending_candidate()
            if candidate is None:
                self.reset_observation()
                return
            if self._unavailable_version == candidate.version:
                return
            if self._context is None or self._context.candidate != candidate:
                self._start(candidate)
            context = self._context
            detected = context.detector.detect(frame)
            context.window.add_frame(timestamp)
            boxes = (context.rule.targets_in_regions(detected)
                     if self.channel.rule == 'absence' else detected)
            if not process_rule:
                return
            observation = context.rule.observe(timestamp, boxes)
            context.window.add_sample(*self.sample_evidence(
                frame, boxes, observation, context.rule, self.binding))
            if not context.window.due(timestamp):
                return
            try:
                with self.sessions() as db:
                    db.execute(text('BEGIN IMMEDIATE'))
                    try:
                        view = self.close_window(
                            db, self.run, self.channel, self.binding, context.window, timestamp,
                            self.actor_id, context.thresholds, context.profile_version,
                            context.candidate.version, route_role='candidate',
                            model_version=context.model_version)
                        db.commit()
                    except Exception:
                        db.rollback()
                        raise
                if view.verdict == 'insufficient':
                    self.reset_rule(context.rule, context.window_rule_state, timestamp)
                elif isinstance(context.rule, PresenceRule):
                    context.window_rule_state = context.rule.state
            finally:
                context.window.reset(timestamp)
        except Exception as error:
            candidate = locals().get('candidate')
            self._unavailable(candidate, error)
