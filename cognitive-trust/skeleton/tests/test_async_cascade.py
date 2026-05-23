"""Tests for the async cascade worker."""

from __future__ import annotations

import time

import pytest

from cogtrust import (
    AttestationRequest,
    AttestationService,
    AttestationType,
    Ed25519Signer,
    LineageStore,
    RevocationIndex,
)
from cogtrust.tiers import default_registry_for_examples
from cogtrust.workers.async_cascade import AsyncRevocationCascade


@pytest.fixture
def env():
    lineage = LineageStore()
    revocation = RevocationIndex()
    tier_reg = default_registry_for_examples()
    signer = Ed25519Signer(identity="async_test", kind="service")
    service = AttestationService(
        signer=signer, lineage=lineage, tier_registry=tier_reg
    )
    async_cascade = AsyncRevocationCascade(
        lineage=lineage, index=revocation,
        max_queue_size=10, num_workers=1, sla_target_ms=60_000,
    )
    async_cascade.start()
    yield {
        "lineage": lineage,
        "revocation": revocation,
        "service": service,
        "async_cascade": async_cascade,
    }
    async_cascade.shutdown(timeout=2.0)


def _issue_intent(service: AttestationService) -> str:
    req = AttestationRequest(
        type=AttestationType.INTENT_ROOT,
        subject={"intent_description": "test"},
        artifact_class="scratch_note",
        intent_root_ref=None,
    )
    return service.issue(req).attestation_id


def test_async_submit_returns_immediately(env):
    intent_id = _issue_intent(env["service"])
    accepted = env["async_cascade"].submit(intent_id, reason="test")
    assert accepted is True


def test_async_cascade_eventually_revokes(env):
    intent_id = _issue_intent(env["service"])
    env["service"].issue(
        AttestationRequest(
            type=AttestationType.GENERATION,
            subject={"artifact_id": "g"},
            artifact_class="code_explanation",
            intent_root_ref=intent_id,
        )
    )

    completion_event = []

    def on_done(summary):
        completion_event.append(summary)

    env["async_cascade"].submit(intent_id, reason="test", on_complete=on_done)

    # Wait for completion (up to 2 seconds).
    deadline = time.time() + 2.0
    while time.time() < deadline and not completion_event:
        time.sleep(0.01)

    assert completion_event, "cascade did not complete within timeout"
    summary = completion_event[0]
    assert summary["derivative_count"] == 1


def test_async_backpressure(env):
    # Fill the queue past capacity. Make sure we don't actually process them
    # all before we check (use unknown attestations that the sync cascade will
    # try and fail on — but we just want enqueue behavior).
    accepted_count = 0
    rejected_count = 0
    # Queue size is 10; submit 50.
    for i in range(50):
        if env["async_cascade"].submit(f"att_fake_{i}", reason="overflow"):
            accepted_count += 1
        else:
            rejected_count += 1
    # Should have rejected at least some. Exact numbers depend on
    # processing speed, but it must be > 0.
    metrics = env["async_cascade"].metrics()
    assert metrics.jobs_rejected_backpressure > 0
    assert accepted_count + rejected_count == 50


def test_async_metrics_reflect_work(env):
    intent_id = _issue_intent(env["service"])
    env["async_cascade"].submit(intent_id, reason="test")

    # Wait for worker to drain.
    deadline = time.time() + 2.0
    while time.time() < deadline:
        m = env["async_cascade"].metrics()
        if m.jobs_completed >= 1:
            break
        time.sleep(0.01)

    m = env["async_cascade"].metrics()
    assert m.jobs_queued >= 1
    assert m.jobs_completed >= 1
    assert m.jobs_in_flight == 0
    # Latency for in-memory should be far under SLA.
    assert m.latency_ms_max < env["async_cascade"].metrics().sla_target_ms


def test_async_queue_depth_visible(env):
    depth_before = env["async_cascade"].queue_depth()
    assert depth_before == 0
