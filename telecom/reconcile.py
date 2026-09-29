"""Stage 4 -- Reconcile and serve.

Compares input, accepted, and rejected counts and totals so a discrepancy
is caught by an explicit check rather than discovered downstream by a BI
tool showing the wrong number.
"""
from __future__ import annotations

from dataclasses import dataclass

from .model import CallDetailRecord, RejectedRecord


@dataclass(frozen=True)
class ReconciliationReport:
    input_count: int
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    conflict_count: int
    accepted_total_rated_minor: int

    @property
    def is_balanced(self) -> bool:
        return self.input_count == (
            self.accepted_count + self.rejected_count + self.duplicate_count + self.conflict_count
        )


def reconcile(
    input_count: int,
    accepted: list[CallDetailRecord],
    rejected: list[RejectedRecord],
    duplicates: list[CallDetailRecord],
    conflicts: list[CallDetailRecord],
) -> ReconciliationReport:
    return ReconciliationReport(
        input_count=input_count,
        accepted_count=len(accepted),
        rejected_count=len(rejected),
        duplicate_count=len(duplicates),
        conflict_count=len(conflicts),
        accepted_total_rated_minor=sum(r.rated_minor for r in accepted),
    )
