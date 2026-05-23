"""Tests for the SQLite-backed lineage store."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from cogtrust import (
    AttestationRequest,
    AttestationService,
    AttestationType,
    Ed25519Signer,
    RevocationCascade,
    RevocationIndex,
    Verifier,
)
from cogtrust.lineage import LineageError
from cogtrust.stores.sqlite_lineage import SqliteLineageStore
from cogtrust.tiers import default_registry_for_examples
from cogtrust.verification import TrustState


@pytest.fixture
def env():
    """E2E environment with SQLite-backed lineage."""
    lineage = SqliteLineageStore(":memory:")
    revocation = RevocationIndex()
    tier_reg = default_registry_for_examples()
    signer = Ed25519Signer(identity="sqlite_test_signer", kind="service")
    service = AttestationService(
        signer=signer, lineage=lineage, tier_registry=tier_reg
    )
    verifier = Verifier(lineage=lineage, revocation=revocation)
    cascade = RevocationCascade(lineage=lineage, index=revocation)
    yield {
        "lineage": lineage,
        "revocation": revocation,
        "service": service,
        "verifier": verifier,
        "cascade": cascade,
    }
    lineage.close()


def _issue_intent(service: AttestationService) -> str:
    req = AttestationRequest(
        type=AttestationType.INTENT_ROOT,
        subject={"intent_description": "test", "user_id": "user_test"},
        artifact_class="scratch_note",
        intent_root_ref=None,
    )
    return service.issue(req).attestation_id


def test_sqlite_basic_issuance(env):
    intent_id = _issue_intent(env["service"])
    status = env["verifier"].verify(intent_id)
    assert status.state == TrustState.VALID


def test_sqlite_persistence_across_handles():
    """Lineage survives reopening the database."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"

        # First handle: insert.
        store1 = SqliteLineageStore(str(db_path))
        signer = Ed25519Signer(identity="t", kind="service")
        registry = default_registry_for_examples()
        service1 = AttestationService(
            signer=signer, lineage=store1, tier_registry=registry
        )
        req = AttestationRequest(
            type=AttestationType.INTENT_ROOT,
            subject={"intent_description": "persists"},
            artifact_class="scratch_note",
            intent_root_ref=None,
        )
        att = service1.issue(req)
        store1.close()

        # Second handle: read.
        store2 = SqliteLineageStore(str(db_path))
        retrieved = store2.get(att.attestation_id)
        assert retrieved is not None
        assert retrieved.attestation_id == att.attestation_id
        assert store2.size() == 1
        assert store2.validate_chain() is True
        store2.close()


def test_sqlite_append_only_triggers_block_update():
    """The DB-level triggers prevent UPDATE on attestations."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        store = SqliteLineageStore(str(db_path))
        signer = Ed25519Signer(identity="t", kind="service")
        registry = default_registry_for_examples()
        service = AttestationService(
            signer=signer, lineage=store, tier_registry=registry
        )
        att_id = _issue_intent(service)

        # Try to UPDATE directly via SQL — must fail.
        raw_conn = sqlite3.connect(str(db_path))
        try:
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                raw_conn.execute(
                    "UPDATE attestations SET signature_value = 'tampered' "
                    "WHERE attestation_id = ?",
                    (att_id,),
                )
        finally:
            raw_conn.close()
            store.close()


def test_sqlite_append_only_triggers_block_delete():
    """The DB-level triggers prevent DELETE on attestations."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        store = SqliteLineageStore(str(db_path))
        signer = Ed25519Signer(identity="t", kind="service")
        registry = default_registry_for_examples()
        service = AttestationService(
            signer=signer, lineage=store, tier_registry=registry
        )
        att_id = _issue_intent(service)

        raw_conn = sqlite3.connect(str(db_path))
        try:
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                raw_conn.execute(
                    "DELETE FROM attestations WHERE attestation_id = ?",
                    (att_id,),
                )
        finally:
            raw_conn.close()
            store.close()


def test_sqlite_duplicate_id_rejected(env):
    intent_id = _issue_intent(env["service"])
    att = env["lineage"].get(intent_id)
    assert att is not None
    with pytest.raises(LineageError, match="already exists"):
        env["lineage"].append(att)


def test_sqlite_descendants_via_intent_root_edge(env):
    intent_id = _issue_intent(env["service"])
    gen = env["service"].issue(
        AttestationRequest(
            type=AttestationType.GENERATION,
            subject={"artifact_id": "g"},
            artifact_class="code_explanation",
            intent_root_ref=intent_id,
        )
    )
    direct = env["lineage"].descendants(intent_id)
    assert gen.attestation_id in direct


def test_sqlite_cascade_works(env):
    intent_id = _issue_intent(env["service"])
    gen = env["service"].issue(
        AttestationRequest(
            type=AttestationType.GENERATION,
            subject={"artifact_id": "g"},
            artifact_class="code_explanation",
            intent_root_ref=intent_id,
        )
    )
    summary = env["cascade"].revoke_with_cascade(intent_id, reason="test")
    assert summary["derivative_count"] == 1
    status = env["verifier"].verify(gen.attestation_id)
    assert status.state == TrustState.DERIVATIVE_REVOKED


def test_sqlite_chain_validation(env):
    _issue_intent(env["service"])
    _issue_intent(env["service"])
    intent3 = _issue_intent(env["service"])
    env["service"].issue(
        AttestationRequest(
            type=AttestationType.GENERATION,
            subject={"artifact_id": "g"},
            artifact_class="code_explanation",
            intent_root_ref=intent3,
        )
    )
    assert env["lineage"].validate_chain() is True


def test_sqlite_chain_head(env):
    head_before = env["lineage"].chain_head()
    assert head_before is None
    att_id = _issue_intent(env["service"])
    head_after = env["lineage"].chain_head()
    assert head_after is not None
    assert head_after[0] == att_id
