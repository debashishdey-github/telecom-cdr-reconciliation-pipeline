"""End-to-end demo wiring the four stages together on a small, readable scenario.

Run with: python3 -m telecom.pipeline
"""
from __future__ import annotations

from .aggregate import aggregate_by_business_date
from .dedupe import dedupe_by_call_id
from .file_tracking import ProcessedFileTracker
from .ingest import validate_batch
from .model import CallDetailRecord, RejectedRecord
from .reconcile import reconcile

# Two legitimate calls from the same subscriber starting in the same second --
# this is exactly the case that a subscriber+timestamp dedupe key would wrongly collapse.
FILE_1 = "cdr_20260901_001.csv"
FILE_1_ROWS = [
    {"call_id": "C-0001", "subscriber_id": "S-1", "start_timestamp": "2026-09-01T14:00:00+00:00",
     "duration_seconds": 120, "rated_minor": 15},
    {"call_id": "C-0002", "subscriber_id": "S-1", "start_timestamp": "2026-09-01T14:00:00+00:00",
     "duration_seconds": 45, "rated_minor": 5},
    # A call at 23:58 US/Eastern local time -- the boundary case the business-date
    # rule exists for. 2026-09-01T23:58 EDT is 2026-09-02T03:58 UTC.
    {"call_id": "C-0003", "subscriber_id": "S-2", "start_timestamp": "2026-09-02T03:58:00+00:00",
     "duration_seconds": 0, "rated_minor": 0},  # a valid, zero-duration unanswered call.
    {"call_id": "C-0004", "subscriber_id": "S-3", "start_timestamp": "not-a-timestamp",
     "duration_seconds": 30, "rated_minor": 4},  # malformed: unparseable timestamp.
]

# FILE_1 redelivered verbatim, plus one new call and one call that conflicts
# with an earlier payload under the same call_id.
FILE_1_REDELIVERED = FILE_1
FILE_2 = "cdr_20260901_002.csv"
FILE_2_ROWS = [
    {"call_id": "C-0001", "subscriber_id": "S-1", "start_timestamp": "2026-09-01T14:00:00+00:00",
     "duration_seconds": 120, "rated_minor": 15},  # identical payload -> a duplicate, not a conflict.
    {"call_id": "C-0002", "subscriber_id": "S-1", "start_timestamp": "2026-09-01T14:00:00+00:00",
     "duration_seconds": 999, "rated_minor": 999},  # same call_id, DIFFERENT payload -> a conflict.
    {"call_id": "C-0005", "subscriber_id": "S-4", "start_timestamp": "2026-09-01T18:00:00+00:00",
     "duration_seconds": 60, "rated_minor": 8},
]


def _demo() -> None:
    tracker = ProcessedFileTracker()
    all_accepted: list[CallDetailRecord] = []
    all_rejected: list[RejectedRecord] = []
    total_input = 0

    for filename, rows in ((FILE_1, FILE_1_ROWS), (FILE_1_REDELIVERED, FILE_1_ROWS), (FILE_2, FILE_2_ROWS)):
        if not tracker.should_ingest(filename):
            print(f"{filename}: skipped, already ingested (redelivery)")
            continue
        accepted, rejected = validate_batch(rows, filename)
        total_input += len(rows)
        all_accepted.extend(accepted)
        all_rejected.extend(rejected)
        tracker.mark_ingested(filename)
        print(f"{filename}: {len(accepted)} accepted, {len(rejected)} rejected at ingest")

    dedupe_result = dedupe_by_call_id(all_accepted)
    print(f"\nafter dedupe: {len(dedupe_result.accepted)} accepted, "
          f"{len(dedupe_result.duplicates)} duplicate(s), {len(dedupe_result.conflicts)} conflict(s)")

    summaries = aggregate_by_business_date(dedupe_result.accepted)
    for s in summaries:
        print(f"  {s.business_date} / {s.source_file}: {s.calls} calls, "
              f"{s.total_duration_seconds}s, {s.total_rated_minor} minor units")

    report = reconcile(total_input, dedupe_result.accepted, all_rejected,
                        dedupe_result.duplicates, dedupe_result.conflicts)
    print(f"\nreconciliation: input={report.input_count} accepted={report.accepted_count} "
          f"rejected={report.rejected_count} duplicates={report.duplicate_count} "
          f"conflicts={report.conflict_count} balanced={report.is_balanced}")


if __name__ == "__main__":
    _demo()
