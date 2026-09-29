# Telecom CDR Reconciliation Pipeline

A small, fully tested reference implementation of a call-detail-record (CDR)
batch pipeline: file-identity tracking, durable call-level deduplication,
timezone-correct business-date derivation, and count/total reconciliation.

This is a **focused reference pipeline**, not a platform. There is no
database, no orchestrator, and no scheduler. Every stage is a plain function
over plain Python data, so the part that is easy to get subtly wrong —
duplicate detection and time-zone handling — is easy to read, test, and
reuse on its own.

## Project status

Built as a teaching companion to the [Telecom CDR batch analytics
playbook](https://datasparkle.academy) on DataSparkle Academy. It implements
that playbook's four stages end to end and is exercised by a test suite that
maps directly onto the playbook's own acceptance checks. It is not
affiliated with, and does not depend on, any carrier's actual billing or
mediation systems.

## Why this is harder than it looks

Two traps account for most of the duplicate and misreported records in a
real CDR pipeline, and both are treated as first-class problems here rather
than edge cases:

- **A redelivered source file.** The same file arriving twice is the most
  common cause of duplicated calls. [`telecom/file_tracking.py`](telecom/file_tracking.py)'s
  `ProcessedFileTracker` checks file identity *before* ingesting a single
  row — a cheaper and more reliable defense than deduplicating thousands of
  rows downstream after the fact.
- **Deduplicating on subscriber + timestamp.** Two genuinely different calls
  from the same subscriber can start in the same second, so that key would
  silently discard a real call.
  [`telecom/dedupe.py`](telecom/dedupe.py)'s `dedupe_by_call_id` keys only on
  the durable `call_id` carried in the source file, and separately flags —
  rather than silently merges — the case where the same `call_id` shows up
  twice with genuinely different payloads (a real data conflict, not a
  redelivery).

The other half of the problem is time:

- **[`telecom/business_date.py`](telecom/business_date.py)** derives
  `business_date` from a single, fixed, documented timezone constant
  (`BUSINESS_TIMEZONE`), never from UTC and never from the server's local
  timezone. A call starting at 23:58 local time is the exact boundary case
  this exists for — get the timezone wrong and it lands on the wrong
  business date entirely.
- **[`telecom/aggregate.py`](telecom/aggregate.py)** sums `duration_seconds`
  and `rated_minor` as two independent totals. Rated amounts are never
  recomputed from duration: that requires the tariff and rounding rules
  applied at the correct grain, and doing it after the fact will not match
  the source system's per-call totals. All money is integer minor units —
  no floats anywhere in the pipeline.

[`telecom/ingest.py`](telecom/ingest.py) validates duration bounds, timestamp
parseability (rejecting naive timestamps outright, since a business date
can't be trusted without knowing what clock produced it), and required
identifiers — while treating a valid zero-duration call (e.g. an unanswered
but still-rated call) as distinct from a malformed record.
[`telecom/reconcile.py`](telecom/reconcile.py) closes the loop by comparing
input, accepted, rejected, duplicate, and conflict counts so nothing goes
missing silently.

## Running it

```bash
pip install -r requirements.txt
python3 -m pytest tests/ -v
python3 -m telecom.pipeline   # ingests two files (one a verbatim redelivery),
                              # dedupes, aggregates, and reconciles, printing
                              # each stage's effect on the batch
```

## What the tests actually check

`tests/test_pipeline.py` maps to the playbook's stated acceptance gates:

- Re-delivering a file — verbatim, filename and all — produces zero
  duplicate calls, both at the tracker level and end to end.
- A call starting at 23:58 local time derives the correct business date
  under the fixed timezone, and a naive or unparseable timestamp is
  rejected rather than guessed at.
- Duration and rated-amount totals are summed independently and reconcile
  exactly against the accepted record set.
- Two different calls from the same subscriber in the same second are both
  kept; an identical call redelivered under a *different* filename is still
  recognized as a duplicate; and a genuinely conflicting payload under the
  same `call_id` is flagged, not silently merged.

## License

MIT — see [LICENSE](LICENSE).
