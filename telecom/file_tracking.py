"""Durable source-file identity tracking.

Checking whether a file has already been ingested, before ingesting any of
its rows, is a cheaper and more reliable defense than deduplicating
thousands of duplicate call rows downstream after a redelivered file has
already been processed once.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProcessedFileTracker:
    _processed: set[str] = field(default_factory=set)

    def should_ingest(self, filename: str) -> bool:
        return filename not in self._processed

    def mark_ingested(self, filename: str) -> None:
        self._processed.add(filename)
