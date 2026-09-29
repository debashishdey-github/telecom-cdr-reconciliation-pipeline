"""Data model for a validated call detail record (CDR)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

MAX_CALL_DURATION_SECONDS = 24 * 60 * 60  # a call longer than a day is bad data, not a real call.


@dataclass(frozen=True)
class CallDetailRecord:
    call_id: str  # the durable, source-assigned identity -- the only safe dedupe key.
    subscriber_id: str
    start_timestamp_utc: datetime  # always timezone-aware, always normalized to UTC.
    duration_seconds: int
    rated_minor: int  # integer minor currency units, never a float.
    source_file: str


@dataclass(frozen=True)
class RejectedRecord:
    source_file: str
    raw: dict
    reason: str
