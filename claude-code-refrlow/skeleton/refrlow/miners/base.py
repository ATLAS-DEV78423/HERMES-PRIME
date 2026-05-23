"""
Base class for all subagents (miners).

A miner has:
  - a class_name (e.g. "file_miner")
  - a set of tasks it supports
  - an execute() method that takes a DispatchRequest and returns a DispatchReport

Miners are stateless. Each dispatch is independent.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from refrlow.protocol import DispatchReport, DispatchRequest, utc_now_iso


class Miner(ABC):
    """Abstract base class for subagent implementations."""

    #: Subagent class name as used in DispatchRequest.subagent.
    class_name: str = ""

    #: Set of task names this miner supports.
    tasks: set[str] = set()

    @abstractmethod
    def execute(self, request: DispatchRequest) -> DispatchReport:
        """
        Execute the dispatch. Return a DispatchReport.

        Implementations should:
          - Validate task-specific params.
          - Respect budget.max_tokens, budget.max_results, budget.ttl_seconds.
          - Set status appropriately (never default to OK without verification).
          - Populate integrity.content_hashes for any files referenced.
        """
        raise NotImplementedError

    # --- helpers for subclasses ---

    def _start(self) -> tuple[float, str]:
        """Return (monotonic_start, iso_started_at)."""
        return time.monotonic(), utc_now_iso()

    def _elapsed_ms(self, start_monotonic: float) -> int:
        return int((time.monotonic() - start_monotonic) * 1000)
