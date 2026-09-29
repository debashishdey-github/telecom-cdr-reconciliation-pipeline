from datetime import datetime, timezone

from telecom.aggregate import aggregate_by_business_date
from telecom.business_date import BUSINESS_TIMEZONE, derive_business_date
from telecom.dedupe import dedupe_by_call_id
from telecom.file_tracking import ProcessedFileTracker
from telecom.ingest import validate_batch, validate_record
from telecom.model import CallDetailRecord, RejectedRecord
from telecom.reconcile import reconcile


def cdr(call_id="C-1", subscriber_id="S-1", start="2026-09-01T14:00:00+00:00",
        duration_seconds=60, rated_minor=10, source_file="f.csv"):
    return CallDetailRecord(
        call_id=call_id, subscriber_id=subscriber_id,
        start_timestamp_utc=datetime.fromisoformat(start), duration_seconds=duration_seconds,
        rated_minor=rated_minor, source_file=source_file,
    )


# --- Check: re-delivering a file does not duplicate calls. ---

def test_processed_file_tracker_rejects_a_redelivered_filename():
    tracker = ProcessedFileTracker()
    assert tracker.should_ingest("cdr_20260901_001.csv") is True
    tracker.mark_ingested("cdr_20260901_001.csv")
    assert tracker.should_ingest("cdr_20260901_001.csv") is False
    assert tracker.should_ingest("cdr_20260901_002.csv") is True


def test_redelivered_file_produces_no_duplicate_calls_end_to_end():
    tracker = ProcessedFileTracker()
    rows = [{"call_id": "C-1", "subscriber_id": "S-1", "start_timestamp": "2026-09-01T14:00:00+00:00",
             "duration_seconds": 60, "rated_minor": 10}]

    ingested: list[CallDetailRecord] = []
    for _ in range(2):  # the same file "arrives" twice.
        if tracker.should_ingest("cdr_20260901_001.csv"):
            accepted, _ = validate_batch(rows, "cdr_20260901_001.csv")
            ingested.extend(accepted)
            tracker.mark_ingested("cdr_20260901_001.csv")

    assert len(ingested) == 1


# --- Check: timezone boundary calls land on the correct business date. ---

def test_business_date_derivation_uses_the_fixed_business_timezone_not_utc():
    # 2026-09-01T23:58 US/Eastern (EDT, UTC-4) is 2026-09-02T03:58 UTC.
    # A pipeline that assumed UTC would derive 2026-09-02, which is wrong.
    start_utc = datetime(2026, 9, 2, 3, 58, tzinfo=timezone.utc)
    assert derive_business_date(start_utc).isoformat() == "2026-09-01"


def test_business_date_derivation_rejects_naive_datetimes():
    naive = datetime(2026, 9, 1, 12, 0)
    try:
        derive_business_date(naive)
        assert False, "expected ValueError for a naive datetime"
    except ValueError:
        pass


def test_ingest_rejects_naive_or_unparseable_timestamps():
    naive_row = {"call_id": "C-1", "subscriber_id": "S-1", "start_timestamp": "2026-09-01T12:00:00",
                 "duration_seconds": 10, "rated_minor": 1}
    garbage_row = {"call_id": "C-2", "subscriber_id": "S-1", "start_timestamp": "not-a-timestamp",
                   "duration_seconds": 10, "rated_minor": 1}
    assert isinstance(validate_record(naive_row, "f.csv"), RejectedRecord)
    assert isinstance(validate_record(garbage_row, "f.csv"), RejectedRecord)


def test_ingest_accepts_a_valid_zero_duration_call_as_distinct_from_malformed():
    zero_duration_row = {"call_id": "C-1", "subscriber_id": "S-1",
                          "start_timestamp": "2026-09-01T12:00:00+00:00",
                          "duration_seconds": 0, "rated_minor": 0}
    result = validate_record(zero_duration_row, "f.csv")
    assert isinstance(result, CallDetailRecord)
    assert result.duration_seconds == 0


# --- Check: rated amounts remain exact and independently reconciled. ---

def test_aggregation_sums_duration_and_rated_amount_as_independent_totals():
    records = [
        cdr(call_id="C-1", start="2026-09-01T14:00:00+00:00", duration_seconds=100, rated_minor=12),
        cdr(call_id="C-2", start="2026-09-01T15:00:00+00:00", duration_seconds=50, rated_minor=7),
    ]
    summaries = aggregate_by_business_date(records)
    assert len(summaries) == 1
    assert summaries[0].total_duration_seconds == 150
    assert summaries[0].total_rated_minor == 19  # exact integer sum, never derived from duration.


def test_reconciliation_report_balances_input_against_all_dispositions():
    accepted = [cdr(call_id="C-1")]
    rejected = [RejectedRecord("f.csv", {}, "bad")]
    duplicates = [cdr(call_id="C-2")]
    conflicts = [cdr(call_id="C-3")]
    report = reconcile(input_count=4, accepted=accepted, rejected=rejected,
                        duplicates=duplicates, conflicts=conflicts)
    assert report.is_balanced
    assert report.accepted_total_rated_minor == 10


# --- Check: deduplication uses a durable call/event identity, not subscriber+timestamp. ---

def test_two_different_calls_from_same_subscriber_same_second_are_both_kept():
    # This is the exact scenario a subscriber+timestamp dedupe key would wrongly collapse.
    same_second = "2026-09-01T14:00:00+00:00"
    a = cdr(call_id="C-1", subscriber_id="S-1", start=same_second, duration_seconds=120, rated_minor=15)
    b = cdr(call_id="C-2", subscriber_id="S-1", start=same_second, duration_seconds=45, rated_minor=5)
    result = dedupe_by_call_id([a, b])
    assert len(result.accepted) == 2
    assert result.duplicates == []


def test_identical_redelivered_payload_is_a_duplicate_not_a_conflict():
    a = cdr(call_id="C-1")
    b = cdr(call_id="C-1")  # identical payload, same call_id.
    result = dedupe_by_call_id([a, b])
    assert len(result.accepted) == 1
    assert len(result.duplicates) == 1
    assert result.conflicts == []


def test_identical_call_redelivered_under_a_different_filename_is_still_a_duplicate():
    # The same call content, but arriving via a different source file -- this must
    # not be misclassified as a conflict just because source_file differs.
    a = cdr(call_id="C-1", source_file="cdr_20260901_001.csv")
    b = cdr(call_id="C-1", source_file="cdr_20260901_002.csv")
    result = dedupe_by_call_id([a, b])
    assert len(result.accepted) == 1
    assert len(result.duplicates) == 1
    assert result.conflicts == []


def test_same_call_id_with_different_payload_is_flagged_as_a_conflict_not_silently_merged():
    a = cdr(call_id="C-1", duration_seconds=60, rated_minor=10)
    b = cdr(call_id="C-1", duration_seconds=999, rated_minor=999)  # same id, different data.
    result = dedupe_by_call_id([a, b])
    assert len(result.accepted) == 1
    assert result.accepted[0].duration_seconds == 60  # the first-seen payload wins, conflict is flagged.
    assert len(result.conflicts) == 1
    assert result.duplicates == []
