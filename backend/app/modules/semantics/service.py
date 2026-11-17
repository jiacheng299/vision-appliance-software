"""Persist the time-decayed profile and judge observation windows.

This module owns its three tables. It never writes run, event or model rows; it
only reads the current profile version so a stale window cannot claim validity.
"""
from datetime import datetime, timezone
from dataclasses import asdict
import hashlib
import json
import re
import time

from sqlalchemy import delete, func, select

from ...shared.errors import Error
from ...shared.models import now, uid
from .. import sources as sources_module
from ..agents.service import get_agent
from .models import ObservationRecord, ProfileAttribute, ProfileEvent, SemanticProfile
from .profile import STATE_CONFLICT, STATE_VALID, attribute_strength
from .schemas import (AttributeInput, AttributeView, IntrinsicInput, ObservationInput,
                      ObservationMetrics, ObservationPage, ObservationThresholds,
                      ObservationView, ProfileEventView, ProfileView, Versions)
from . import observe

DEFAULT_VIEW_VERSION = 'v1'
KEY_PATTERN = re.compile(r'^[A-Za-z0-9_.-]{1,64}$')
CURSOR_LIMIT = 200
# Conservative floors for a window to count as an observation. Occlusion and
# target scale stay unmeasured because neither can be verified from one frame,
# and an unmeasured gate is only allowed to block absence, never a detection.
DEFAULT_THRESHOLDS = dict(min_fps=1.0, min_roi_visible_ratio=0.9,
                          max_overexposure_ratio=0.2, min_blur_score=20.0,
                          max_occlusion_ratio=None, min_target_scale_px=None)


def thresholds_for(*, window_seconds, max_gap_seconds=None, **overrides):
    values = dict(DEFAULT_THRESHOLDS, **overrides)
    values['max_gap_seconds'] = max_gap_seconds
    values['min_window_seconds'] = window_seconds * 0.9
    return ObservationThresholds(**values)


def epoch() -> float:
    return time.time()


def _check_key(key):
    if not KEY_PATTERN.match(key or ''):
        raise Error(422, 'attribute_key_invalid', '属性名只能由字母、数字、下划线、点和短横线组成。')


def _profile(db, source_id, view_version=None, create=False):
    query = select(SemanticProfile).where(SemanticProfile.source_id == source_id)
    if view_version is not None:
        query = query.where(SemanticProfile.view_version == view_version)
    row = db.scalars(query.order_by(SemanticProfile.updated_at.desc())).first()
    if row is None and create:
        sources_module.get_source(db, source_id)
        row = SemanticProfile(id=uid(), source_id=source_id,
                              view_version=view_version or DEFAULT_VIEW_VERSION,
                              intrinsic={}, runtime={}, version=0)
        db.add(row)
        db.flush()
    return row


def _touch(row):
    row.version += 1
    row.updated_at = now()
    return row


def _attribute_views(db, profile_id, at):
    views = []
    for row in db.scalars(select(ProfileAttribute).where(ProfileAttribute.profile_id == profile_id)
                          .order_by(ProfileAttribute.key)).all():
        result = attribute_strength(observed_at=row.observed_at, at=at,
                                    confidence=row.confidence, tau_seconds=row.tau_seconds,
                                    hard_expiry_at=row.hard_expiry_at,
                                    conflict=row.state == STATE_CONFLICT)
        views.append(AttributeView(key=row.key, value=row.value, source_kind=row.source_kind,
                                   source_frame_ts=row.source_frame_ts, roi=row.roi,
                                   observed_at=row.observed_at, confidence=row.confidence,
                                   tau_seconds=row.tau_seconds, hard_expiry_at=row.hard_expiry_at,
                                   stored_state=row.state, state=result.state,
                                   strength=round(result.strength, 6), usable=result.usable,
                                   reason=result.reason, version=row.version))
    return views


def read_profile(db, source_id, at=None):
    sources_module.get_source(db, source_id)
    evaluated_at = epoch() if at is None else at
    row = _profile(db, source_id)
    if row is None:
        return ProfileView(source_id=source_id, view_version=DEFAULT_VIEW_VERSION, version=0,
                           intrinsic={}, runtime={}, attributes=[], evaluated_at=evaluated_at,
                           updated_at=now())
    return ProfileView(source_id=row.source_id, view_version=row.view_version, version=row.version,
                       intrinsic=row.intrinsic, runtime=row.runtime,
                       attributes=_attribute_views(db, row.id, evaluated_at),
                       evaluated_at=evaluated_at, updated_at=row.updated_at)


def _append_event(db, profile, *, kind, summary, attribute=None, previous=None,
                  current=None, actor='workspace'):
    """One append-only line per version bump; the shared timeline reads these."""
    db.add(ProfileEvent(id=uid(), source_id=profile.source_id, profile_id=profile.id,
                        version=profile.version, kind=kind, attribute=attribute,
                        previous=previous, current=current, summary=summary, actor=actor,
                        created_at=now()))


def update_intrinsic(db, source_id, body: IntrinsicInput):
    sources_module.get_source(db, source_id)
    row = _profile(db, source_id, body.view_version, create=True)
    before = dict(row.intrinsic or {})
    if body.values:
        row.intrinsic = {**row.intrinsic, **body.values}
    _touch(row)
    changed = sorted({key for key in body.values if before.get(key) != body.values[key]})
    summary = ('更新固有层：' + '、'.join(changed)) if changed else '固有层无实际变化'
    _append_event(db, row, kind='intrinsic', summary=summary)
    db.flush()
    return read_profile(db, source_id)


def upsert_attribute(db, source_id, key, body: AttributeInput):
    _check_key(key)
    sources_module.get_source(db, source_id)
    profile = _profile(db, source_id, create=True)
    observed_at = epoch() if body.observed_at is None else body.observed_at
    if body.hard_expiry_at is not None and body.hard_expiry_at <= observed_at:
        raise Error(422, 'attribute_expiry_invalid', '硬失效时刻必须晚于观测时刻。')
    row = db.scalars(select(ProfileAttribute).where(ProfileAttribute.profile_id == profile.id,
                                                   ProfileAttribute.key == key)).first()
    previous_label = _label_of(row.value or {}) if row is not None else None
    state = STATE_CONFLICT if body.conflict else STATE_VALID
    if row is None:
        row = ProfileAttribute(id=uid(), profile_id=profile.id, key=key, version=1)
        db.add(row)
    else:
        row.version += 1
    row.value = body.value
    row.source_kind = body.source_kind
    row.source_frame_ts = body.source_frame_ts
    row.roi = body.roi
    row.observed_at = observed_at
    row.confidence = body.confidence
    row.tau_seconds = body.tau_seconds
    row.hard_expiry_at = body.hard_expiry_at
    row.state = state
    row.updated_at = now()
    _touch(profile)
    _append_event(db, profile, kind='attribute_write',
                  summary=f'写入动态属性 {key}',
                  attribute=key, previous=previous_label,
                  current=_label_of(body.value or {}))
    db.flush()
    return read_profile(db, source_id)


def _label_of(value):
    label = value.get('label') if isinstance(value, dict) else None
    return None if label is None else str(label)


def delete_attribute(db, source_id, key):
    _check_key(key)
    row = _profile(db, source_id)
    if row is not None:
        removed = db.scalars(select(ProfileAttribute).where(ProfileAttribute.profile_id == row.id,
                                                           ProfileAttribute.key == key)).first()
        db.execute(delete(ProfileAttribute).where(ProfileAttribute.profile_id == row.id,
                                                  ProfileAttribute.key == key))
        _touch(row)
        if removed is not None:
            _append_event(db, row, kind='attribute_delete', summary=f'删除动态属性 {key}',
                          attribute=key, previous=_label_of(removed.value or {}))
        db.flush()
    return read_profile(db, source_id)


def set_runtime(db, source_id, values):
    """运行层由执行器写入；没有画像时静默返回，避免读取被观测对象时造数据。"""
    row = _profile(db, source_id)
    if row is None:
        return None
    row.runtime = {**row.runtime, **values}
    db.flush()
    return row


def _current_profile_version(db, source_id):
    row = _profile(db, source_id)
    return None if row is None else row.version


def profile_version_for(db, source_id):
    """Public: the executor stamps windows with the version it actually ran under."""
    return _current_profile_version(db, source_id)


def record_observation(db, agent_id, actor_id, body: ObservationInput):
    get_agent(db, agent_id)
    sources_module.get_source(db, body.source_id)
    versions = body.versions
    expected = body.expected_versions.model_dump() if body.expected_versions else {}
    current_profile = _current_profile_version(db, body.source_id)
    if body.versions.profile_version is not None and current_profile is not None:
        # The profile version is server-known truth: a window cannot self-declare it.
        expected['profile_version'] = current_profile
    verdict, gates, reasons = observe.evaluate(metrics=body.metrics, thresholds=body.thresholds,
                                               detection_count=body.detection_count,
                                               path_complete=body.path_complete,
                                               versions=versions, expected_versions=expected,
                                               nodes_completed=body.nodes_completed)
    record = ObservationRecord(id=uid(), agent_id=agent_id, actor_id=actor_id, run_id=body.run_id,
                               source_id=body.source_id, task_key=body.task_key, roi=body.roi,
                               window_start=body.window_start, window_end=body.window_end,
                               route_version=body.versions.route_version,
                               profile_version=body.versions.profile_version,
                               model_version=body.versions.model_version,
                               path_id=body.path_id, verdict=verdict,
                               detection_count=body.detection_count,
                               metrics=body.metrics.model_dump(),
                               thresholds=body.thresholds.model_dump(),
                               gates=[asdict(gate) for gate in gates], reasons=list(reasons),
                               created_at=now())
    db.add(record)
    db.flush()
    return _observation_view(record)


def _observation_view(row):
    return ObservationView(id=row.id, agent_id=row.agent_id, run_id=row.run_id,
                           source_id=row.source_id, task_key=row.task_key, roi=row.roi,
                           window_start=row.window_start, window_end=row.window_end,
                           route_version=row.route_version, profile_version=row.profile_version,
                           model_version=row.model_version, path_id=row.path_id,
                           verdict=row.verdict, detection_count=row.detection_count,
                           metrics=ObservationMetrics(**row.metrics),
                           thresholds=ObservationThresholds(**row.thresholds),
                           gates=row.gates, reasons=row.reasons, created_at=row.created_at)


def _cursor(agent_id, actor_id, filters, sequence=None):
    identity = json.dumps([agent_id, actor_id, filters], sort_keys=True, separators=(',', ':'))
    prefix = hashlib.sha256(identity.encode()).hexdigest()[:24]
    return prefix if sequence is None else f'{prefix}:{sequence}'


def _parse_cursor(value, agent_id, actor_id, filters):
    if value is None:
        return None
    prefix = _cursor(agent_id, actor_id, filters)
    try:
        head, raw = value.split(':')
        if head != prefix or not raw.isdigit() or len(raw) > 19:
            raise ValueError()
        return int(raw)
    except (ValueError, AttributeError):
        raise Error(422, 'invalid_cursor', '观察记录游标无效，请重新加载列表。') from None


def list_observations(db, agent_id, actor_id, *, source_id=None, verdict=None, run_id=None,
                      task_key=None, limit=50, cursor=None):
    get_agent(db, agent_id)
    filters = {'source_id': source_id, 'verdict': verdict, 'run_id': run_id, 'task_key': task_key}
    filters = {key: value for key, value in filters.items() if value}
    sequence = _parse_cursor(cursor, agent_id, actor_id, filters)
    limit = min(max(int(limit), 1), CURSOR_LIMIT)
    query = select(ObservationRecord).where(ObservationRecord.agent_id == agent_id,
                                            ObservationRecord.actor_id == actor_id)
    if filters.get('source_id'):
        query = query.where(ObservationRecord.source_id == filters['source_id'])
    if filters.get('verdict'):
        query = query.where(ObservationRecord.verdict == filters['verdict'])
    if filters.get('run_id'):
        query = query.where(ObservationRecord.run_id == filters['run_id'])
    if filters.get('task_key'):
        query = query.where(ObservationRecord.task_key == filters['task_key'])
    if sequence is not None:
        query = query.where(ObservationRecord.sequence < sequence)
    rows = list(db.scalars(query.order_by(ObservationRecord.sequence.desc()).limit(limit + 1)))
    items = rows[:limit]
    counts = dict(db.execute(select(ObservationRecord.verdict, func.count())
                             .where(ObservationRecord.agent_id == agent_id,
                                    ObservationRecord.actor_id == actor_id)
                             .group_by(ObservationRecord.verdict)).all())
    return ObservationPage(items=[_observation_view(row) for row in items],
                           next_cursor=_cursor(agent_id, actor_id, filters, items[-1].sequence)
                           if len(rows) > limit else None,
                           summary={key: int(value) for key, value in counts.items()})


def list_events(db, source_id, *, limit=50):
    """Newest-first profile version events for one source."""
    sources_module.get_source(db, source_id)
    rows = db.scalars(select(ProfileEvent).where(ProfileEvent.source_id == source_id)
                      .order_by(ProfileEvent.sequence.desc()).limit(min(max(limit, 1), 200))).all()
    return [ProfileEventView(id=row.id, source_id=row.source_id, version=row.version,
                             kind=row.kind, attribute=row.attribute, previous=row.previous,
                             current=row.current, summary=row.summary, actor=row.actor,
                             created_at=row.created_at) for row in rows]

def observation(db, agent_id, actor_id, observation_id):
    """One window-level record, including its gate-by-gate detail."""
    get_agent(db, agent_id)
    row = db.scalars(select(ObservationRecord)
                     .where(ObservationRecord.id == observation_id,
                            ObservationRecord.agent_id == agent_id,
                            ObservationRecord.actor_id == actor_id)).first()
    if row is None:
        raise Error(404, 'observation_not_found', '观察记录不存在。')
    return _observation_view(row)