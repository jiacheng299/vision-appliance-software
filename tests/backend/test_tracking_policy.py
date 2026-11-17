"""追踪策略接口：契约、注册表诚实性与与旧实现的行为等价。"""
import math
import random

import pytest

from app.modules.tracking import registry
from app.modules.tracking.heuristic import HeuristicIoUTracker
from app.modules.tracking.policy import Decision, Observation, TrackerPolicy, detection_from_box
from app.modules.tracking.runtime import TrackerRuntime, observation_from

PERSON = {'label': 'person', 'x': .4, 'y': .2, 'width': .2, 'height': .6, 'confidence': .9}


class LegacyTracker:
    """Reference copy of the previous in-rule tracker, kept as an oracle."""

    def __init__(self, timeout_seconds):
        self.timeout = timeout_seconds
        self.tracks = {}
        self.sequence = 0

    def update(self, timestamp, boxes):
        detections = [dict(box) for box in boxes if self._valid(box)]
        for track in self.tracks.values():
            if track['missing_since'] is None:
                track['missing_since'] = (track['last_seen']
                                          if timestamp - track['last_seen'] > self.timeout
                                          else timestamp)
        pairs = []
        for track in self.tracks.values():
            if (track['missing_since'] is not None
                    and timestamp - track['missing_since'] > self.timeout):
                continue
            tx = track['box']['x'] + track['box']['width'] / 2
            ty = track['box']['y'] + track['box']['height'] / 2
            for index, box in enumerate(detections):
                bx = box['x'] + box['width'] / 2
                by = box['y'] + box['height'] / 2
                distance = math.hypot(tx - bx, ty - by)
                overlap = self._iou(track['box'], box)
                if overlap >= .05 or distance <= .2:
                    pairs.append((max(overlap, 1 - distance), track['id'], index))
        used_tracks, used_detections, output = set(), set(), []
        for _, identifier, index in sorted(pairs, reverse=True):
            if identifier in used_tracks or index in used_detections:
                continue
            track = self.tracks[identifier]
            track['box'], track['last_seen'], track['missing_since'] = detections[index], timestamp, None
            used_tracks.add(identifier)
            used_detections.add(index)
            output.append((identifier, detections[index]))
        for index, box in enumerate(detections):
            if index in used_detections:
                continue
            self.sequence += 1
            identifier = f'person-{self.sequence}'
            self.tracks[identifier] = {'id': identifier, 'box': box, 'last_seen': timestamp,
                                       'missing_since': None}
            output.append((identifier, box))
        self.tracks = {identifier: track for identifier, track in self.tracks.items()
                       if track['missing_since'] is None
                       or timestamp - track['missing_since'] <= self.timeout}
        return tuple(sorted(output, key=lambda item: item[0]))

    @staticmethod
    def _valid(box):
        if not isinstance(box, dict) or box.get('label') != 'person':
            return False
        values = [box.get(key) for key in ('x', 'y', 'width', 'height')]
        return (all(type(value) in (int, float) and math.isfinite(value) for value in values)
                and values[2] > 0 and values[3] > 0)

    @staticmethod
    def _iou(left, right):
        lx1, ly1, lx2, ly2 = left['x'], left['y'], left['x'] + left['width'], left['y'] + left['height']
        rx1, ry1, rx2, ry2 = right['x'], right['y'], right['x'] + right['width'], right['y'] + right['height']
        overlap = max(0, min(lx2, rx2) - max(lx1, rx1)) * max(0, min(ly2, ry2) - max(ly1, ry1))
        union = left['width'] * left['height'] + right['width'] * right['height'] - overlap
        return overlap / union if union > 0 else 0


def random_boxes(rng, count):
    boxes = []
    for _ in range(count):
        x = round(rng.uniform(0, .8), 3)
        y = round(rng.uniform(0, .6), 3)
        boxes.append({'label': 'person', 'x': x, 'y': y, 'width': round(rng.uniform(.05, .18), 3),
                      'height': round(rng.uniform(.2, .35), 3), 'confidence': .9})
    return boxes


def test_the_policy_runtime_reproduces_the_previous_tracker_exactly():
    rng = random.Random(20261117)
    legacy = LegacyTracker(5.0)
    runtime = TrackerRuntime(HeuristicIoUTracker(), timeout_seconds=5.0)
    timestamp = 0.0
    for step in range(120):
        timestamp += rng.choice([.2, .5, 1.0, 2.0, 6.0])
        boxes = random_boxes(rng, rng.choice([0, 0, 1, 1, 2, 3]))
        expected = legacy.update(timestamp, boxes)
        actual = runtime.update(observation_from(timestamp, boxes))
        assert [(track.id, track.box) for track in actual] == list(expected)


def test_the_heuristic_policy_is_a_member_of_the_protocol():
    assert isinstance(HeuristicIoUTracker(), TrackerPolicy)


def test_enrolment_of_a_learned_policy_is_refused_while_it_is_not_installed():
    from app.shared.errors import Error
    with pytest.raises(Error) as error:
        registry.create('marl-association')
    assert error.value.status == 503
    assert '尚未安装' in error.value.message
    with pytest.raises(Error) as unknown:
        registry.create('does-not-exist')
    assert unknown.value.status == 404


def test_the_registry_states_plainly_what_is_missing():
    entries = {item['name']: item for item in registry.describe()}
    assert entries['heuristic-iou']['installed'] is True
    assert entries['heuristic-iou']['calibrated'] is True
    learned = entries['marl-association']
    assert learned['installed'] is False and learned['calibrated'] is False
    assert learned['kind'] == 'learned'
    assert any('不在本仓库' in item for item in learned['requires'])
    assert any('没有训练循环' in item for item in learned['limitations'])


def test_the_observation_contract_drops_invalid_detections_at_the_boundary():
    observation = observation_from(3.0, [PERSON, {'label': 'car', 'x': .1, 'y': .1, 'width': .1,
                                                 'height': .1}, {'label': 'person', 'x': .1,
                                                                 'y': .1, 'width': 0,
                                                                 'height': .1}])
    assert len(observation.detections) == 1
    assert observation.detections[0].label == 'person'
    assert observation.detections[0].x == .4


def test_a_policy_only_proposes_and_the_framework_owns_the_tracks():
    class Garbage:
        name = 'garbage'

        def reset(self): pass

        def decide(self, observation, tracks):
            return Decision(associations=(('nobody', 0), ('x', 99)), new_detections=(5,))

        def describe(self): return {}

    runtime = TrackerRuntime(Garbage(), timeout_seconds=5.0)
    observation = Observation(timestamp=1.0,
                             detections=(detection_from_box(PERSON),))
    tracks = runtime.update(observation)
    assert tracks == ()          # every proposed edge was invalid, so nothing exists


def test_a_policy_cannot_mutate_its_way_into_the_track_table():
    class Ghost:
        name = 'ghost'

        def reset(self): pass

        def decide(self, observation, tracks):
            for track in tracks:
                track.box['x'] = 9.0
            return Decision(new_detections=tuple(range(len(observation.detections))))

        def describe(self): return {}

    runtime = TrackerRuntime(Ghost(), timeout_seconds=5.0)
    first = Observation(timestamp=1.0, detections=(detection_from_box(PERSON),))
    runtime.update(first)
    runtime.update(Observation(timestamp=1.5, detections=(detection_from_box(PERSON),)))
    # The frame the framework kept still says where the person really was.
    assert runtime.tracks[0].box['x'] == .4


def test_reset_clears_state_and_the_policy():
    runtime = TrackerRuntime(HeuristicIoUTracker(), timeout_seconds=5.0)
    runtime.update(Observation(timestamp=1.0, detections=(detection_from_box(PERSON),)))
    assert runtime.tracks
    runtime.reset()
    assert runtime.tracks == ()
