"""
Async revocation cascade worker.

The synchronous reference in cogtrust/revocation.py is correct but
blocks the request that triggers revocation. For production we want:

  - Non-blocking revocation requests (caller returns immediately)
  - Bounded concurrency (don't fan out 10k cascades at once)
  - Backpressure (reject new revocations if queue is saturated)
  - SLA monitoring (target: 60s end-to-end per CT-I5)
  - Audit on cascade progress

This module provides AsyncRevocationCascade. It wraps the synchronous
core with a thread-pool worker, a bounded queue, and SLA metrics.

For very high revocation rates, replace the threading.Thread executor
with a real queue system (Redis, NATS, SQS). The interface stays
identical.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from cogtrust.lineage import LineageStore
from cogtrust.revocation import RevocationCascade, RevocationIndex

logger = logging.getLogger("cogtrust.workers.async_cascade")


@dataclass
class CascadeJob:
    attestation_id: str
    reason: str
    submitted_at: float
    on_complete: Optional[Callable[[dict], None]] = None


@dataclass
class CascadeMetrics:
    """Snapshot of cascade worker state."""

    jobs_queued: int = 0
    jobs_in_flight: int = 0
    jobs_completed: int = 0
    jobs_failed: int = 0
    jobs_rejected_backpressure: int = 0

    latency_ms_p50: float = 0.0
    latency_ms_p99: float = 0.0
    latency_ms_max: float = 0.0

    sla_target_ms: int = 60_000  # CT-I5: 60 seconds
    sla_breaches: int = 0


class AsyncRevocationCascade:
    """
    Async wrapper around RevocationCascade.

    Caller calls submit() and gets a job-id immediately. A worker thread
    pulls from a bounded queue and runs the actual cascade. Metrics are
    exposed for SLA monitoring.

    Concurrency model: single worker thread by default. SQLite-backed
    LineageStore is single-writer; multiple workers would contend.
    For Postgres-backed stores, raise `num_workers` to parallelize.
    """

    def __init__(
        self,
        lineage: LineageStore,
        index: RevocationIndex,
        max_queue_size: int = 1000,
        num_workers: int = 1,
        sla_target_ms: int = 60_000,
    ) -> None:
        self._sync_cascade = RevocationCascade(lineage, index)
        self._queue: queue.Queue[CascadeJob] = queue.Queue(maxsize=max_queue_size)
        self._num_workers = num_workers
        self._sla_target_ms = sla_target_ms
        self._latencies: list[float] = []
        self._latencies_lock = threading.Lock()
        self._metrics_lock = threading.Lock()
        self._metrics = CascadeMetrics(sla_target_ms=sla_target_ms)
        self._shutdown = threading.Event()
        self._workers: list[threading.Thread] = []

    def start(self) -> None:
        for i in range(self._num_workers):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"cascade-worker-{i}",
                daemon=True,
            )
            t.start()
            self._workers.append(t)

    def shutdown(self, timeout: float = 5.0) -> None:
        self._shutdown.set()
        # Push sentinels to wake workers.
        for _ in self._workers:
            try:
                self._queue.put_nowait(
                    CascadeJob(
                        attestation_id="__shutdown__",
                        reason="",
                        submitted_at=time.time(),
                    )
                )
            except queue.Full:
                pass
        for t in self._workers:
            t.join(timeout=timeout)

    def submit(
        self,
        attestation_id: str,
        reason: str,
        on_complete: Optional[Callable[[dict], None]] = None,
    ) -> bool:
        """
        Submit a cascade job. Returns True if enqueued, False if rejected
        due to backpressure.
        """
        job = CascadeJob(
            attestation_id=attestation_id,
            reason=reason,
            submitted_at=time.time(),
            on_complete=on_complete,
        )
        try:
            self._queue.put_nowait(job)
            with self._metrics_lock:
                self._metrics.jobs_queued += 1
            return True
        except queue.Full:
            with self._metrics_lock:
                self._metrics.jobs_rejected_backpressure += 1
            logger.warning(
                "cascade queue full; rejecting %s", attestation_id
            )
            return False

    def metrics(self) -> CascadeMetrics:
        """Return a snapshot of current metrics."""
        with self._metrics_lock, self._latencies_lock:
            if self._latencies:
                sorted_lat = sorted(self._latencies)
                p50 = sorted_lat[len(sorted_lat) // 2]
                p99_idx = max(0, int(len(sorted_lat) * 0.99) - 1)
                p99 = sorted_lat[p99_idx]
                lmax = sorted_lat[-1]
            else:
                p50 = p99 = lmax = 0.0

            return CascadeMetrics(
                jobs_queued=self._metrics.jobs_queued,
                jobs_in_flight=self._metrics.jobs_in_flight,
                jobs_completed=self._metrics.jobs_completed,
                jobs_failed=self._metrics.jobs_failed,
                jobs_rejected_backpressure=self._metrics.jobs_rejected_backpressure,
                latency_ms_p50=p50,
                latency_ms_p99=p99,
                latency_ms_max=lmax,
                sla_target_ms=self._sla_target_ms,
                sla_breaches=self._metrics.sla_breaches,
            )

    def queue_depth(self) -> int:
        return self._queue.qsize()

    # --- internals ---

    def _worker_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                job = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if job.attestation_id == "__shutdown__":
                break
            self._process_job(job)

    def _process_job(self, job: CascadeJob) -> None:
        with self._metrics_lock:
            self._metrics.jobs_in_flight += 1
        try:
            summary = self._sync_cascade.revoke_with_cascade(
                job.attestation_id, reason=job.reason
            )
            latency_ms = (time.time() - job.submitted_at) * 1000.0

            with self._latencies_lock:
                self._latencies.append(latency_ms)
                # Keep last 1024 samples.
                if len(self._latencies) > 1024:
                    self._latencies = self._latencies[-1024:]

            with self._metrics_lock:
                self._metrics.jobs_completed += 1
                if latency_ms > self._sla_target_ms:
                    self._metrics.sla_breaches += 1
                    logger.error(
                        "cascade SLA breach: %.0fms > %dms (target) for %s",
                        latency_ms, self._sla_target_ms, job.attestation_id,
                    )

            if job.on_complete:
                try:
                    job.on_complete(summary)
                except Exception:  # pylint: disable=broad-except
                    logger.exception("cascade on_complete callback failed")
        except Exception:  # pylint: disable=broad-except
            with self._metrics_lock:
                self._metrics.jobs_failed += 1
            logger.exception(
                "cascade job failed for %s", job.attestation_id
            )
        finally:
            with self._metrics_lock:
                self._metrics.jobs_in_flight -= 1
