"""
End-to-end tests for the attestation service, lineage, revocation, verification.
"""

from __future__ import annotations

import time

import pytest

from cogtrust import (
    AttestationRequest,
    AttestationService,
    AttestationType,
    Ed25519Signer,
    LineageStore,
    RevocationCascade,
    RevocationIndex,
    TierRegistry,
    Verifier,
)
from cogtrust.service import AttestationServiceError
from cogtrust.tiers import default_registry_for_examples
from cogtrust.verification import TrustState


@pytest.fixture
def env():
    """Set up a minimal end-to-end environment."""
    lineage = LineageStore()
    revocation = RevocationIndex()
    tier_reg = default_registry_for_examples()
    service_signer = Ed25519Signer(identity="attestation_service_test", kind="service")
    service = AttestationService(
        signer=service_signer, lineage=lineage, tier_registry=tier_reg
    )
    verifier = Verifier(lineage=lineage, revocation=revocation)
    cascade = RevocationCascade(lineage=lineage, index=revocation)
    return {
        "lineage": lineage,
        "revocation": revocation,
        "tier_registry": tier_reg,
        "service": service,
        "verifier": verifier,
        "cascade": cascade,
        "signer": service_signer,
    }


def _issue_intent_root(service: AttestationService, expires_at: str | None = None) -> str:
    req = AttestationRequest(
        type=AttestationType.INTENT_ROOT,
        subject={"intent_description": "test work", "user_id": "user_alice"},
        artifact_class="scratch_note",  # tier 0 — minimal ceremony
        intent_root_ref=None,
        expires_at=expires_at,
    )
    att = service.issue(req)
    return att.attestation_id


def test_intent_root_issuance(env):
    att_id = _issue_intent_root(env["service"])
    status = env["verifier"].verify(att_id)
    assert status.state == TrustState.VALID
    assert status.chain_length == 1
    assert status.cache_hit is False


def test_intent_root_requires_no_predecessor(env):
    req = AttestationRequest(
        type=AttestationType.INTENT_ROOT,
        subject={"intent_description": "test"},
        artifact_class="scratch_note",
        intent_root_ref=None,
    )
    att = env["service"].issue(req)
    assert att.intent_root_ref is None


def test_non_root_requires_intent_root(env):
    with pytest.raises(ValueError, match="requires intent_root_ref"):
        AttestationRequest(
            type=AttestationType.GENERATION,
            subject={"artifact_id": "foo"},
            artifact_class="code_explanation",
            intent_root_ref=None,
        )


def test_generation_chains_to_intent(env):
    intent_id = _issue_intent_root(env["service"])
    gen_req = AttestationRequest(
        type=AttestationType.GENERATION,
        subject={
            "artifact_id": "art_001",
            "artifact_hash": "sha256:abcdef",
            "model": {"name": "claude-test"},
        },
        artifact_class="code_explanation",  # tier 1
        intent_root_ref=intent_id,
    )
    gen_att = env["service"].issue(gen_req)
    status = env["verifier"].verify(gen_att.attestation_id)
    assert status.state == TrustState.VALID
    assert status.chain_length == 2  # generation + intent


def test_missing_intent_root_rejected(env):
    with pytest.raises(AttestationServiceError, match="not found"):
        env["service"].issue(
            AttestationRequest(
                type=AttestationType.GENERATION,
                subject={"artifact_id": "x"},
                artifact_class="code_explanation",
                intent_root_ref="att_does_not_exist",
            )
        )


def test_unknown_artifact_class_rejected(env):
    intent_id = _issue_intent_root(env["service"])
    with pytest.raises(ValueError, match="unknown artifact_class"):
        env["service"].issue(
            AttestationRequest(
                type=AttestationType.GENERATION,
                subject={},
                artifact_class="mystery_class_not_registered",
                intent_root_ref=intent_id,
            )
        )


def test_revocation_cascade(env):
    intent_id = _issue_intent_root(env["service"])
    gen_att = env["service"].issue(
        AttestationRequest(
            type=AttestationType.GENERATION,
            subject={"artifact_id": "art_x", "artifact_hash": "sha256:foo"},
            artifact_class="code_explanation",
            intent_root_ref=intent_id,
        )
    )

    # Initially valid.
    assert env["verifier"].verify(gen_att.attestation_id).state == TrustState.VALID

    # Revoke the intent root; cascade.
    summary = env["cascade"].revoke_with_cascade(intent_id, reason="test_revocation")
    assert summary["derivative_count"] == 1

    # Now generation is derivative_revoked.
    status = env["verifier"].verify(gen_att.attestation_id)
    assert status.state == TrustState.DERIVATIVE_REVOKED


def test_verification_cache(env):
    intent_id = _issue_intent_root(env["service"])
    # First verification — cache miss.
    s1 = env["verifier"].verify(intent_id)
    assert s1.cache_hit is False
    # Second verification — cache hit.
    s2 = env["verifier"].verify(intent_id)
    assert s2.cache_hit is True
    assert s2.state == s1.state


def test_revocation_invalidates_cache(env):
    intent_id = _issue_intent_root(env["service"])
    env["verifier"].verify(intent_id)  # warm cache
    # Revoke something (anything) to bump version.
    other_intent = _issue_intent_root(env["service"])
    env["cascade"].revoke_with_cascade(other_intent, reason="bump")
    # Now verifier sees new revocation version; cache key changes.
    s = env["verifier"].verify(intent_id)
    assert s.cache_hit is False  # because cache key differs


def test_lineage_hash_chain_intact(env):
    _issue_intent_root(env["service"])
    intent2 = _issue_intent_root(env["service"])
    env["service"].issue(
        AttestationRequest(
            type=AttestationType.GENERATION,
            subject={"artifact_id": "g"},
            artifact_class="code_explanation",
            intent_root_ref=intent2,
        )
    )
    assert env["lineage"].validate_chain() is True


def test_lineage_rejects_duplicate_id(env):
    intent_id = _issue_intent_root(env["service"])
    intent = env["lineage"].get(intent_id)
    assert intent is not None
    # Attempt to re-append same attestation.
    from cogtrust.lineage import LineageError

    with pytest.raises(LineageError, match="already exists"):
        env["lineage"].append(intent)


def test_high_tier_requires_review(env):
    """A T3+ artifact's approval attestation requires a review predecessor."""
    intent_id = _issue_intent_root(env["service"])
    # Issue a T3 generation (pull_request_create is tier 3).
    gen_att = env["service"].issue(
        AttestationRequest(
            type=AttestationType.GENERATION,
            subject={"artifact_id": "pr_001"},
            artifact_class="pull_request_create",
            intent_root_ref=intent_id,
        )
    )
    # Attempt approval without review → reject.
    with pytest.raises(AttestationServiceError, match="reviewer attestations"):
        env["service"].issue(
            AttestationRequest(
                type=AttestationType.APPROVAL,
                subject={"approver_id": "user_alice"},
                artifact_class="pull_request_create",
                intent_root_ref=intent_id,
                predecessor_refs=[gen_att.attestation_id],
            )
        )


def test_chain_back_to_intent(env):
    intent_id = _issue_intent_root(env["service"])
    gen_att = env["service"].issue(
        AttestationRequest(
            type=AttestationType.GENERATION,
            subject={"artifact_id": "g"},
            artifact_class="code_explanation",
            intent_root_ref=intent_id,
            predecessor_refs=[],
        )
    )
    chain = env["lineage"].chain_back_to_intent(gen_att.attestation_id)
    assert intent_id in chain
    assert gen_att.attestation_id in chain


def test_signature_actually_verifies(env):
    """Make sure the signing/verification round-trip works."""
    intent_id = _issue_intent_root(env["service"])
    intent = env["lineage"].get(intent_id)
    assert intent is not None
    # Verifier checks the signature.
    status = env["verifier"].verify(intent_id)
    assert status.state == TrustState.VALID


def test_tampered_signature_fails_verification(env):
    """If we mutate signature value, verification must fail."""
    intent_id = _issue_intent_root(env["service"])
    intent = env["lineage"].get(intent_id)
    assert intent is not None
    # Tamper: replace signature with garbage (fresh cache to force recompute).
    intent.signature_value = "AAAA"  # invalid base64-ish, will fail
    env["verifier"].invalidate_cache()
    status = env["verifier"].verify(intent_id)
    assert status.state == TrustState.SIGNATURE_INVALID
