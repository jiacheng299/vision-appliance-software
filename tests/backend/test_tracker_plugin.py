"""外部追踪策略的加载：只接受显式 module:attribute，且必须满足协议。"""
import sys
import types

import pytest

from app.modules.tracking import registry
from app.modules.tracking.policy import Decision


@pytest.fixture
def plugin(monkeypatch):
    """Register a throwaway module that exposes a valid MARL-shaped policy."""
    module = types.ModuleType('tests_fake_marl')

    class Policy:
        name = 'fake-marl'
        track_prefix = 't'

        def reset(self): pass

        def decide(self, observation, tracks):
            return Decision(new_detections=tuple(range(len(observation.detections))))

        def describe(self): return {'name': self.name, 'kind': 'learned'}

    module.Policy = Policy
    module.Broken = lambda: object()          # 不满足协议
    module.Explode = lambda: 1 / 0            # 初始化就抛错
    monkeypatch.setitem(sys.modules, 'tests_fake_marl', module)
    return module


def test_an_explicit_spec_loads_a_third_party_policy(plugin):
    policy = registry.create('tests_fake_marl:Policy')
    assert policy.name == 'fake-marl'
    assert hasattr(policy, 'decide')


def test_a_policy_that_does_not_implement_the_protocol_is_refused(plugin):
    from app.shared.errors import Error
    with pytest.raises(Error) as error:
        registry.create('tests_fake_marl:Broken')
    assert error.value.code == 'tracker_policy_incompatible'


def test_a_policy_that_fails_to_initialise_is_reported_not_swallowed(plugin):
    from app.shared.errors import Error
    with pytest.raises(Error) as error:
        registry.create('tests_fake_marl:Explode')
    assert error.value.status == 503 and '初始化失败' in error.value.message


def test_a_missing_module_or_attribute_is_reported(plugin):
    from app.shared.errors import Error
    with pytest.raises(Error) as missing_module:
        registry.create('tests_does_not_exist:Policy')
    assert missing_module.value.code == 'tracker_policy_unavailable'
    with pytest.raises(Error) as missing_attribute:
        registry.create('tests_fake_marl:NotThere')
    assert missing_attribute.value.code == 'tracker_policy_unavailable'


def test_a_spec_without_an_attribute_is_rejected():
    from app.shared.errors import Error
    with pytest.raises(Error) as error:
        registry.create('tests_fake_marl:')
    assert error.value.code in ('tracker_policy_spec_invalid', 'tracker_policy_unknown')


def test_the_builtin_and_the_reserved_slot_still_behave_as_before():
    from app.shared.errors import Error
    assert registry.create('heuristic-iou').name == 'heuristic-iou'
    with pytest.raises(Error) as error:
        registry.create('marl-association')
    assert error.value.code == 'tracker_policy_not_installed'


def test_the_default_configuration_still_uses_the_heuristic_policy():
    from app.shared.config import Config
    assert Config().tracker_policy == 'heuristic-iou'
