"""Business-date derivation in a single, fixed, documented timezone.

A call starting at 23:58 local time can land on the wrong business date
entirely if the pipeline silently assumes UTC or the server's local
timezone instead of the contractually agreed one. There is exactly one
timezone constant, used everywhere business_date is derived, so the live
and batch paths can never quietly disagree.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

BUSINESS_TIMEZONE = ZoneInfo("America/New_York")


def derive_business_date(start_timestamp_utc: datetime) -> date:
    if start_timestamp_utc.tzinfo is None:
        raise ValueError("start_timestamp_utc must be timezone-aware")
    return start_timestamp_utc.astimezone(BUSINESS_TIMEZONE).date()
