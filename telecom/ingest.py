"""Stage 1 -- Ingest and validate.

Validates duration bounds, timestamp parseability, and identifiers, and
separates genuinely malformed records from valid zero-duration calls (e.g.
an unanswered call that was still rated) -- those are not the same thing and
must not be rejected together.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .model import MAX_CALL_DURATION_SECONDS, CallDetailRecord, RejectedRecord

REQUIRED_FIELDS = ("call_id", "subscriber_id", "start_timestamp", "duration_seconds", "rated_minor")


def _parse_timestamp(raw: str) -> datetime | None:
    try:
        ts = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if ts.tzinfo is None:
        # A naive timestamp cannot be trusted for business-date derivation: we
        # don't know what clock it was read from, so we don't guess.
        return None
    return ts.astimezone(timezone.utc)


def validate_record(raw: dict, source_file: str) -> CallDetailRecord | RejectedRecord:
    for field_name in REQUIRED_FIELDS:
        if raw.get(field_name) in (None, ""):
            return RejectedRecord(source_file, raw, f"missing required field: {field_name}")

    start = _parse_timestamp(str(raw["start_timestamp"]))
    if start is None:
        return RejectedRecord(source_file, raw, "unparseable or timezone-naive start_timestamp")

    try:
        duration_seconds = int(raw["duration_seconds"])
        rated_minor = int(raw["rated_minor"])
    except (TypeError, ValueError):
        return RejectedRecord(source_file, raw, "duration_seconds and rated_minor must be integers")

    if duration_seconds < 0 or duration_seconds > MAX_CALL_DURATION_SECONDS:
        return RejectedRecord(source_file, raw, f"duration_seconds out of bounds: {duration_seconds}")
    if rated_minor < 0:
        return RejectedRecord(source_file, raw, f"rated_minor cannot be negative: {rated_minor}")

    return CallDetailRecord(
        call_id=str(raw["call_id"]),
        subscriber_id=str(raw["subscriber_id"]),
        start_timestamp_utc=start,
        duration_seconds=duration_seconds,
        rated_minor=rated_minor,
        source_file=source_file,
    )


def validate_batch(raw_records: list[dict], source_file: str) -> tuple[list[CallDetailRecord], list[RejectedRecord]]:
    accepted: list[CallDetailRecord] = []
    rejected: list[RejectedRecord] = []
    for raw in raw_records:
        result = validate_record(raw, source_file)
        if isinstance(result, CallDetailRecord):
            accepted.append(result)
        else:
            rejected.append(result)
    return accepted, rejected
