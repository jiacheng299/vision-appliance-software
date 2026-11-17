"""漂移判定（M9 / S10）：只有新证据确认的变化才算漂移。

属性仅因时间衰减而失效时，系统只能说"不再知道"，因此只触发补充抽帧；
把"过期"当成"场景反向变化"，会让一次漏采样直接改写路由。
"""
from dataclasses import dataclass

CONFIRMED = 'confirmed'
EXPIRED = 'expired'
BASELINE = 'baseline'


@dataclass(frozen=True)
class DriftFinding:
    attribute: str
    kind: str
    previous: str | None
    current: str | None
    reason: str

    @property
    def is_drift(self):
        return self.kind == CONFIRMED


def label_of(attribute):
    """The semantic value an attribute carries, if any."""
    value = attribute.value or {}
    if isinstance(value, dict) and value.get('label') is not None:
        return str(value['label'])
    return None


def labels_of(attributes):
    return {attribute.key: label_of(attribute)
            for attribute in attributes if attribute.usable and label_of(attribute) is not None}


def cursor_of(attributes, previous=None):
    """The newest observation time we have already taken into account."""
    stamps = [attribute.observed_at for attribute in attributes if attribute.usable]
    if not stamps:
        return previous
    newest = max(stamps)
    return newest if previous is None else max(previous, newest)


def detect(attributes, *, previous_labels=None, cursor=None):
    """Split attribute news into confirmed drift and mere expiry.

    `cursor` is the newest evidence already accounted for. Anything observed at or
    before it carries no news; anything after it may confirm a change.
    """
    previous_labels = previous_labels or {}
    findings = []
    for attribute in attributes:
        current = label_of(attribute)
        previous = previous_labels.get(attribute.key)
        if not attribute.usable:
            if previous is not None:
                findings.append(DriftFinding(
                    attribute.key, EXPIRED, previous, None,
                    '属性已过期，转为未知并触发补充抽帧，不认定场景反向变化'))
            continue
        if cursor is not None and attribute.observed_at <= cursor:
            continue
        if previous is None:
            findings.append(DriftFinding(attribute.key, BASELINE, None, current,
                                         '首次确认该属性，作为后续比较的基线'))
        elif previous != current:
            findings.append(DriftFinding(attribute.key, CONFIRMED, previous, current,
                                         '新帧或设备证据确认属性发生变化'))
    return tuple(findings)


def drifted_keys(findings):
    return tuple(finding.attribute for finding in findings if finding.is_drift)


def expired_keys(findings):
    return tuple(finding.attribute for finding in findings if finding.kind == EXPIRED)
