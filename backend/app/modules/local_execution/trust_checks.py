"""Read a bounded set of typed diagnostics from the local audit logs."""
import json
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field

from ...schemas import DTO
from ...shared.errors import Error

MAX_TAIL_BYTES = 64 * 1024
RECORDS_LIMIT = 30


class TrustCheckDTO(DTO):
    source_id: str
    source_kind: Literal['file', 'camera']
    run_id: str
    channel_id: str
    observed_at: AwareDatetime
    reason: Literal['invalid_sample_time', 'sample_time_not_increasing', 'sample_gap',
                    'observation_interrupted', 'unstable_detection', 'event_scope_mismatch',
                    'event_media_range_invalid', 'evidence_unavailable', 'observer_failed']
    start_seconds: float | None = Field(default=None, allow_inf_nan=False)
    end_seconds: float | None = Field(default=None, allow_inf_nan=False)
    event_id: str | None = None


def _read_tail(root: Path, suffix: str) -> bytes:
    try:
        path = (root / 'logs' / f'model-safety.jsonl{suffix}').resolve()
        if root not in path.parents:
            raise OSError('Audit log is outside the data directory')
        with path.open('rb') as stream:
            offset = max(0, stream.seek(0, 2) - MAX_TAIL_BYTES)
            stream.seek(offset)
            data = stream.read(MAX_TAIL_BYTES)
    except FileNotFoundError:
        return b''
    except OSError:
        raise Error(503, 'trust_checks_unavailable', '模型防护记录暂时无法读取。', retryable=True) from None
    return data.partition(b'\n')[2] if offset else data


def read_trust_checks(var_root: Path, agent_id: str, source_id: str | None) -> list[TrustCheckDTO]:
    records, seen = [], set()
    root = var_root.resolve()
    for suffix in ('', '.1', '.2'):
        for line in reversed(_read_tail(root, suffix).splitlines()):
            if not line or len(line) > 2048 or line in seen:
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict) or row.get('agent_id') != agent_id:
                    continue
                if source_id is not None and row.get('source_id') != source_id:
                    continue
                fields = {key: row[key] for key in TrustCheckDTO.model_fields if key in row}
                records.append(TrustCheckDTO.model_validate(fields))
            except (ValueError, RecursionError):
                continue
            seen.add(line)
            if len(records) >= RECORDS_LIMIT * 3:
                return records
    return records
