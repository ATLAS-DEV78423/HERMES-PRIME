"""Tests for the reviewer UI skeleton."""

from __future__ import annotations

import time

import pytest

from cogtrust import (
    AttestationRequest,
    AttestationService,
    AttestationType,
    Ed25519Signer,
    LineageStore,
)
from cogtrust.reviewer_ui import (
    ArtifactPresenter,
    ReviewDecision,
    ReviewerSession,
    ReviewSubmitter,
    SessionState,
    Verdict,
)
from cogtrust.tiers import default_registry_for_examples
from cogtrust.verification import Verifier


@pytest.fixture
def env():
    lineage = LineageStore()
    tier_reg = default_registry_for_examples()
    service_signer = Ed25519Signer(identity="svc_test", kind="service")
    service = AttestationService(
        signer=service_signer, lineage=lineage, tier_registry=tier_reg
    )
    verifier = Verifier(lineage=lineage, revocation=__import__(
        "cogtrust"
    ).RevocationIndex())

    # Personal-signing AttestationService factory:
    # in production each personal signer talks to its own personal-key
    # signing endpoint. For tests we construct a service-per-signer.
    def factory(personal_signer):
        return AttestationService(
            signer=personal_signer,
            lineage=lineage,
            tier_registry=tier_reg,
        )

    presenter = ArtifactPresenter(lineage=lineage, verifier=verifier)
    submitter = ReviewSubmitter(
        lineage=lineage, tier_registry=tier_reg, service_factory=factory,
    )

    yield {
        "lineage": lineage,
        "tier_reg": tier_reg,
        "service": service,
        "verifier": verifier,
        "presenter": presenter,
        "submitter": submitter,
    }


def _issue_intent(service, artifact_class: str = "scratch_note") -> str:
    req = AttestationRequest(
        type=AttestationType.INTENT_ROOT,
        subject={"intent_description": "review test", "user_id": "user_test"},
        artifact_class=artifact_class,
        intent_root_ref=None,
    )
    return service.issue(req).attestation_id


def _issue_t3_generation(service, intent_id):
    """Issue a tier-3 (pull_request_create) generation attestation."""
    return service.issue(
        AttestationRequest(
            type=AttestationType.GENERATION,
            subject={
                "artifact_id": "art_pr",
                "artifact_hash": "sha256:test",
                "model": {"name": "test-model", "version": "v1"},
            },
            artifact_class="pull_request_create",
            intent_root_ref=intent_id,
        )
    )


def _personal_session(reviewer_id: str = "user_alice") -> ReviewerSession:
    personal_signer = Ed25519Signer(identity=reviewer_id, kind="personal")
    return ReviewerSession(
        reviewer_id=reviewer_id,
        personal_signer=personal_signer,
        authenticated_at=time.time(),
    )


def test_session_requires_personal_signer():
    bad_signer = Ed25519Signer(identity="svc", kind="service")
    with pytest.raises(ValueError, match="personal-kind signer"):
        ReviewerSession(
            reviewer_id="user_x",
            personal_signer=bad_signer,
            authenticated_at=time.time(),
        )


def test_session_expires():
    session = _personal_session()
    session.session_ttl_seconds = 0
    time.sleep(0.01)
    assert session.state == SessionState.EXPIRED


def test_session_fresh_auth_window():
    session = _personal_session()
    session.fresh_auth_window_seconds = 5
    assert session.is_fresh_authenticated() is True
    session.authenticated_at = time.time() - 100
    assert session.is_fresh_authenticated() is False


def test_session_fatigue_grows_with_short_decisions():
    session = _personal_session()
    # Simulate many fast reviews.
    for _ in range(15):
        session.record_review(decision_latency_ms=500.0)  # half a second
    assert session.fatigue_score() > 0.5


def test_presenter_shows_artifact_details(env):
    intent_id = _issue_intent(env["service"], artifact_class="pull_request_create")
    gen = _issue_t3_generation(env["service"], intent_id)
    view = env["presenter"].present(gen.attestation_id)
    assert view.artifact_class == "pull_request_create"
    assert view.tier == 3
    assert view.intent_root_id == intent_id
    assert view.intent_description == "review test"
    assert view.model_identity == "test-model"


def test_presenter_includes_warnings_for_invalid_chain(env):
    intent_id = _issue_intent(env["service"], artifact_class="pull_request_create")
    gen = _issue_t3_generation(env["service"], intent_id)

    # Revoke the intent root.
    from cogtrust.revocation import RevocationCascade, RevocationIndex
    revocation = RevocationIndex()
    cascade = RevocationCascade(env["lineage"], revocation)
    cascade.revoke_with_cascade(intent_id, reason="test")

    # New verifier sees the revocation.
    verifier = Verifier(lineage=env["lineage"], revocation=revocation)
    presenter = ArtifactPresenter(lineage=env["lineage"], verifier=verifier)
    view = presenter.present(gen.attestation_id)
    assert view.trust_state != "valid"
    assert len(view.warnings) > 0


def test_submitter_rejects_expired_session(env):
    intent_id = _issue_intent(env["service"], artifact_class="pull_request_create")
    gen = _issue_t3_generation(env["service"], intent_id)

    session = _personal_session()
    session.session_ttl_seconds = 0
    time.sleep(0.01)

    decision = ReviewDecision(
        target_artifact_id=gen.attestation_id,
        verdict=Verdict.APPROVED,
        comments="looks fine",
        items_inspected=["diff", "tests"],
        decision_started_at=time.time(),
        decision_completed_at=time.time() + 1.0,
    )

    result = env["submitter"].submit(session, decision)
    assert result.success is False
    assert result.refusal_reason == "session_expired"


def test_submitter_issues_attestation_for_t3(env):
    intent_id = _issue_intent(env["service"], artifact_class="pull_request_create")
    gen = _issue_t3_generation(env["service"], intent_id)

    session = _personal_session()
    decision = ReviewDecision(
        target_artifact_id=gen.attestation_id,
        verdict=Verdict.APPROVED,
        comments="looks fine",
        items_inspected=["diff", "tests"],
        decision_started_at=time.time(),
        decision_completed_at=time.time() + 10.0,  # 10s decision
    )

    result = env["submitter"].submit(session, decision)
    assert result.success is True
    assert result.attestation is not None
    assert result.attestation.type == AttestationType.REVIEW
    assert result.attestation.subject["verdict"] == "approved"


def test_submitter_refuses_when_fatigued(env):
    intent_id = _issue_intent(env["service"], artifact_class="pull_request_create")
    gen = _issue_t3_generation(env["service"], intent_id)

    session = _personal_session()
    # Pre-load fatigue: 30 fast reviews.
    for _ in range(30):
        session.record_review(decision_latency_ms=200.0)
    assert session.fatigue_score() >= 0.7

    decision = ReviewDecision(
        target_artifact_id=gen.attestation_id,
        verdict=Verdict.APPROVED,
        comments="",
        items_inspected=[],
        decision_started_at=time.time(),
        decision_completed_at=time.time() + 0.5,
    )
    result = env["submitter"].submit(session, decision)
    assert result.success is False
    assert "fatigue" in (result.refusal_reason or "")


def test_submitter_target_must_be_generation(env):
    intent_id = _issue_intent(env["service"], artifact_class="pull_request_create")
    # Try to review an intent_root (not a generation).
    session = _personal_session()
    decision = ReviewDecision(
        target_artifact_id=intent_id,
        verdict=Verdict.APPROVED,
        comments="",
        items_inspected=[],
        decision_started_at=time.time(),
        decision_completed_at=time.time() + 1.0,
    )
    result = env["submitter"].submit(session, decision)
    assert result.success is False
    assert result.refusal_reason == "target_is_not_generation"
