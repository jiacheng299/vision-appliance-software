"""画像版本事件与合并时间线：把「画像变了」和「路由变了」画在同一条轴上。"""
import time

import pytest

from app.modules.routing import state as routing_state
from app.modules.semantics import service as semantics
from app.modules.semantics.schemas import AttributeInput, IntrinsicInput

ACTOR = 'workspace'


@pytest.fixture
def seeded(app):
    from app.shared.models import Source
    from app.modules.agents.models import Agent
    with app.state.sessions() as db:
        db.add(Source(id='cam', name='摄像头', kind='camera', status='online',
                      width=960, height=540))
        db.add(Agent(id='agent', name='任务', description='', owner_id=ACTOR))
        db.commit()
    return app


def events(app, limit=20):
    with app.state.sessions() as db:
        return semantics.list_events(db, 'cam', limit=limit)


def test_intrinsic_write_records_a_versioned_event(seeded):
    with seeded.state.sessions() as db:
        semantics.update_intrinsic(db, 'cam', IntrinsicInput(values={'resolution': '960x540'}))
        db.commit()
    rows = events(seeded)
    assert len(rows) == 1
    assert rows[0].kind == 'intrinsic' and rows[0].version == 1
    assert 'resolution' in rows[0].summary


def test_attribute_writes_keep_the_previous_label(seeded):
    now = time.time()
    with seeded.state.sessions() as db:
        semantics.upsert_attribute(db, 'cam', 'lighting', AttributeInput(
            value={'label': 'daylight'}, source_kind='frame', observed_at=now,
            confidence=0.8, hard_expiry_at=now + 600))
        db.commit()
        semantics.upsert_attribute(db, 'cam', 'lighting', AttributeInput(
            value={'label': 'strong_glare'}, source_kind='frame', observed_at=now + 1,
            confidence=0.8, hard_expiry_at=now + 600))
        db.commit()
    newest, older = events(seeded)[:2]
    assert older.previous is None and older.current == 'daylight'
    assert newest.previous == 'daylight' and newest.current == 'strong_glare'
    assert newest.attribute == 'lighting'
    assert newest.version > older.version


def test_deleting_an_attribute_is_recorded_with_what_was_removed(seeded):
    now = time.time()
    with seeded.state.sessions() as db:
        semantics.upsert_attribute(db, 'cam', 'weather', AttributeInput(
            value={'label': 'snow'}, source_kind='frame', observed_at=now,
            confidence=0.7, hard_expiry_at=now + 600))
        db.commit()
        semantics.delete_attribute(db, 'cam', 'weather')
        db.commit()
    newest = events(seeded)[0]
    assert newest.kind == 'attribute_delete' and newest.attribute == 'weather'
    assert newest.previous == 'snow' and newest.current is None


def test_deleting_a_missing_attribute_records_nothing_extra(seeded):
    with seeded.state.sessions() as db:
        semantics.delete_attribute(db, 'cam', 'never_existed')
        db.commit()
    assert events(seeded) == []


def test_the_timeline_merges_profile_and_route_entries_in_time_order(seeded):
    now = time.time()
    with seeded.state.sessions() as db:
        semantics.update_intrinsic(db, 'cam', IntrinsicInput(values={'resolution': '960x540'}))
        db.commit()
        routing_state.propose(db, 'agent', ACTOR, channel_id='ch', source_id='cam',
                              rule='absence')
        db.commit()
        semantics.upsert_attribute(db, 'cam', 'lighting', AttributeInput(
            value={'label': 'daylight'}, source_kind='frame', observed_at=now,
            confidence=0.8, hard_expiry_at=now + 600))
        db.commit()
    with seeded.state.sessions() as db:
        entries = routing_state.timeline(db, 'agent', ACTOR, channel_id='ch', source_id='cam')
    origins = [entry.origin for entry in entries]
    assert 'profile' in origins and 'route' in origins
    times = [entry.at for entry in entries]
    assert times == sorted(times, reverse=True)
    # 最新的应该是刚写入的画像属性事件
    assert entries[0].origin == 'profile' and entries[0].attribute == 'lighting'
    assert any(entry.version.startswith('route-') for entry in entries)
    assert all(entry.version for entry in entries)


def test_the_timeline_endpoint_returns_both_origins(seeded, client):
    now = time.time()
    client.put('/api/v1/sources/cam/semantic-profile',
               json={'values': {'resolution': '960x540'}})
    client.put('/api/v1/sources/cam/semantic-profile/attributes/lighting',
               json={'value': {'label': 'daylight'}, 'source_kind': 'frame',
                     'observed_at': now, 'confidence': 0.8, 'hard_expiry_at': now + 600})
    client.post('/api/v1/agents/agent/routing/propose',
                json={'channel_id': 'ch', 'source_id': 'cam', 'rule': 'absence'})
    response = client.get('/api/v1/agents/agent/routing/timeline',
                          params={'channel_id': 'ch', 'source_id': 'cam'})
    assert response.status_code == 200
    rows = response.json()
    assert {row['origin'] for row in rows} == {'profile', 'route'}
    assert any(row['kind'] == 'intrinsic' for row in rows)
    assert client.get('/api/v1/sources/missing/semantic-profile/events').status_code == 404
