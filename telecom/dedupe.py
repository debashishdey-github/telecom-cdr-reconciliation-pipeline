"""Stage 2 -- Deduplicate by a durable call identity.

Subscriber ID plus start timestamp is deliberately NOT used as the dedupe
key: two genuinely different calls from the same subscriber can start in the
same second, and collapsing them on that key would silently drop a real
call. Only the call_id carried in the source file itself is safe to key on.
"""
from __future__ import annotations

from dataclasses import dataclass

from .model import CallDetailRecord


@dataclass(frozen=True)
class DedupeResult:
    accepted: list[CallDetailRecord]
    duplicates: list[CallDetailRecord]
    conflicts: list[CallDetailRecord]


def _call_content(record: CallDetailRecord) -> tuple:
    """The fields that define whether two rows describe the same call.

    source_file is deliberately excluded: the same call can legitimately be
    redelivered under a different filename (a re-run, a different feed
    mechanism), and that alone must not turn an otherwise-identical payload
    into a false conflict.
    """
    return (record.subscriber_id, record.start_timestamp_utc, record.duration_seconds, record.rated_minor)


def dedupe_by_call_id(records: list[CallDetailRecord]) -> DedupeResult:
    by_id: dict[str, CallDetailRecord] = {}
    duplicates: list[CallDetailRecord] = []
    conflicts: list[CallDetailRecord] = []

    for record in records:
        existing = by_id.get(record.call_id)
        if existing is None:
            by_id[record.call_id] = record
        elif _call_content(existing) == _call_content(record):
            duplicates.append(record)
        else:
            # Same call_id, different payload: a genuine conflict, not a simple
            # redelivery. It must be flagged, never silently overwritten or dropped.
            conflicts.append(record)

    return DedupeResult(accepted=list(by_id.values()), duplicates=duplicates, conflicts=conflicts)
