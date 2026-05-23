"""
Refrlow dispatcher: deterministic spine of the architecture.

The dispatcher receives DispatchRequest objects from the main agent,
validates them against policy, routes to the appropriate subagent,
and returns validated DispatchReport objects.

The dispatcher contains *no LLM logic in its critical path*. All policy
decisions are deterministic. This is by design (see Hermes doctrine P1).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from refrlow.miners.base import Miner
from refrlow.protocol import (
    Budget,
    DispatchReport,
    DispatchRequest,
    Status,
    utc_now_iso,
)
from refrlow.reports import ReportValidationError, validate_report

logger = logging.getLogger("refrlow.dispatcher")


@dataclass
class DispatchPolicy:
    """Operator-configurable policy for dispatch acceptance."""

    # Per-turn caps.
    max_dispatches_per_turn: int = 12
    max_tokens_per_turn: int = 25_000

    # Per-class concurrency limits.
    max_concurrent_per_class: dict[str, int] = field(
        default_factory=lambda: {
            "file_miner": 8,
            "grep_miner": 4,
            "ast_miner": 4,
            "summarizer": 2,
            "validator": 4,
            "task_runner": 1,
            "diff_miner": 4,
            "doc_miner": 2,
        }
    )

    # Per-class budget caps (overridable downward by request, never up).
    max_budget_per_class: dict[str, Budget] = field(
        default_factory=lambda: {
            "file_miner": Budget(max_tokens=2000, ttl_seconds=10),
            "grep_miner": Budget(max_tokens=5000, ttl_seconds=15),
            "ast_miner": Budget(max_tokens=5000, ttl_seconds=20),
            "summarizer": Budget(max_tokens=1200, ttl_seconds=30),
            "validator": Budget(max_tokens=3000, ttl_seconds=60),
            "task_runner": Budget(max_tokens=10000, ttl_seconds=300),
            "diff_miner": Budget(max_tokens=3000, ttl_seconds=10),
            "doc_miner": Budget(max_tokens=2000, ttl_seconds=30),
        }
    )

    # Max chain depth.
    max_chain_depth: int = 3


class Dispatcher:
    """
    The deterministic spine.

    Usage:
        dispatcher = Dispatcher(policy=DispatchPolicy(), workspace_root="/path")
        dispatcher.register(FileMiner())
        dispatcher.register(GrepMiner())
        ...
        report = dispatcher.dispatch(request)
    """

    def __init__(
        self,
        policy: DispatchPolicy,
        workspace_root: str,
        audit_sink: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self.policy = policy
        self.workspace_root = workspace_root
        self.audit_sink = audit_sink or self._default_audit_sink
        self._miners: dict[str, Miner] = {}
        self._turn_dispatch_count = 0
        self._turn_token_total = 0
        self._chain_depths: dict[str, int] = {}

    def register(self, miner: Miner) -> None:
        """Register a subagent class."""
        if miner.class_name in self._miners:
            raise ValueError(f"Subagent class already registered: {miner.class_name}")
        self._miners[miner.class_name] = miner
        logger.info("registered subagent class: %s", miner.class_name)

    def begin_turn(self) -> None:
        """Reset per-turn counters. Call at the start of each main-agent turn."""
        self._turn_dispatch_count = 0
        self._turn_token_total = 0
        self._chain_depths.clear()

    def dispatch(self, request: DispatchRequest) -> DispatchReport:
        """
        Route a dispatch request, returning a validated report.

        This is the single entry point. It applies policy, executes the
        subagent, validates the report, and audits.
        """
        # Per-turn budget enforcement.
        if self._turn_dispatch_count >= self.policy.max_dispatches_per_turn:
            return self._build_denial(
                request,
                "dispatch_count_exceeded",
                f"per-turn dispatch limit reached "
                f"({self.policy.max_dispatches_per_turn})",
            )
        if (
            self._turn_token_total + request.budget.max_tokens
            > self.policy.max_tokens_per_turn
        ):
            return self._build_denial(
                request,
                "dispatch_token_budget_exceeded",
                f"per-turn token budget would be exceeded "
                f"(have {self._turn_token_total}, "
                f"request {request.budget.max_tokens}, "
                f"cap {self.policy.max_tokens_per_turn})",
            )

        # Chain depth check.
        if request.parent_request_id:
            parent_depth = self._chain_depths.get(request.parent_request_id, 0)
            new_depth = parent_depth + 1
            if new_depth > self.policy.max_chain_depth:
                return self._build_denial(
                    request,
                    "chain_depth_exceeded",
                    f"chain depth {new_depth} exceeds max "
                    f"{self.policy.max_chain_depth}",
                )
            self._chain_depths[request.request_id] = new_depth
        else:
            self._chain_depths[request.request_id] = 1

        # Workspace root check.
        if not request.scope.root.startswith(self.workspace_root):
            return self._build_denial(
                request,
                "scope_outside_workspace",
                f"scope root {request.scope.root} not under "
                f"workspace {self.workspace_root}",
            )

        # Class registration check.
        miner = self._miners.get(request.subagent)
        if miner is None:
            return self._build_denial(
                request,
                "unknown_subagent_class",
                f"subagent class '{request.subagent}' not registered",
            )

        # Task allowed by class?
        if request.task not in miner.tasks:
            return self._build_denial(
                request,
                "unknown_task",
                f"task '{request.task}' not supported by "
                f"subagent '{request.subagent}'",
            )

        # Budget cap enforcement (cannot widen beyond class cap).
        class_cap = self.policy.max_budget_per_class.get(request.subagent)
        if class_cap:
            request.budget = Budget(
                max_tokens=min(request.budget.max_tokens, class_cap.max_tokens),
                max_results=min(request.budget.max_results, class_cap.max_results),
                max_bytes_per_result=min(
                    request.budget.max_bytes_per_result, class_cap.max_bytes_per_result
                ),
                ttl_seconds=min(request.budget.ttl_seconds, class_cap.ttl_seconds),
            )

        # Execute.
        self._audit("dispatch_start", request.to_dict())
        start = time.monotonic()
        started_at = utc_now_iso()

        try:
            report = miner.execute(request)
        except Exception as exc:  # pylint: disable=broad-except
            elapsed_ms = int((time.monotonic() - start) * 1000)
            report = DispatchReport(
                request_id=request.request_id,
                subagent=request.subagent,
                task=request.task,
                status=Status.ERROR,
                result={},
                started_at=started_at,
                completed_at=utc_now_iso(),
                elapsed_ms=elapsed_ms,
                error_message=str(exc),
            )
            logger.exception("subagent execution failed: %s", request.request_id)

        # Validate.
        try:
            report = validate_report(report, request)
        except ReportValidationError as ve:
            logger.error("report validation failed: %s", ve)
            # Replace report with a quarantine notice.
            report = DispatchReport(
                request_id=request.request_id,
                subagent=request.subagent,
                task=request.task,
                status=Status.ERROR,
                result={"quarantined": True, "reason": ve.reason},
                started_at=started_at,
                completed_at=utc_now_iso(),
                elapsed_ms=int((time.monotonic() - start) * 1000),
                error_message=f"report quarantined: {ve.reason}",
            )

        # Account.
        self._turn_dispatch_count += 1
        self._turn_token_total += report.tokens_used

        self._audit("dispatch_complete", report.to_dict())
        return report

    def _build_denial(
        self,
        request: DispatchRequest,
        reason: str,
        message: str,
    ) -> DispatchReport:
        now = utc_now_iso()
        return DispatchReport(
            request_id=request.request_id,
            subagent=request.subagent,
            task=request.task,
            status=Status.DENIED,
            result={},
            started_at=now,
            completed_at=now,
            elapsed_ms=0,
            denial_reason=reason,
            error_message=message,
        )

    def _audit(self, event: str, payload: dict) -> None:
        try:
            self.audit_sink({"event": event, "payload": payload})
        except Exception:  # pylint: disable=broad-except
            logger.exception("audit sink failed")

    @staticmethod
    def _default_audit_sink(record: dict) -> None:
        logger.info("audit: %s", record.get("event"))
