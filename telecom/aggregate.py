"""Stage 3 -- Aggregate with correct time.

Duration and rated amount are summed as two separate aggregates. Neither is
ever derived from the other here: recomputing a rated amount from a summed
duration requires the tariff and rounding rules applied at the correct
grain, and doing it after the fact will very likely not match the source
system's per-call rated totals.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from .business_date import derive_business_date
from .model import CallDetailRecord


@dataclass(frozen=True)
class DailySummary:
    business_date: date
    source_file: str
    calls: int
    total_duration_seconds: int
    total_rated_minor: int


def aggregate_by_business_date(records: list[CallDetailRecord]) -> list[DailySummary]:
    groups: dict[tuple[date, str], list[CallDetailRecord]] = defaultdict(list)
    for record in records:
        key = (derive_business_date(record.start_timestamp_utc), record.source_file)
        groups[key].append(record)

    return [
        DailySummary(
            business_date=business_date,
            source_file=source_file,
            calls=len(group),
            total_duration_seconds=sum(r.duration_seconds for r in group),
            total_rated_minor=sum(r.rated_minor for r in group),
        )
        for (business_date, source_file), group in sorted(groups.items())
    ]
