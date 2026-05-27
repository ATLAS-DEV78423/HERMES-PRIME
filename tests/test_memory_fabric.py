from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hermes_prime.contracts import (
    IntentRoot,
    MemoryClaim,
    MemoryTier,
    TrustState,
)
from hermes_prime.memory import DepthPolicy, MemoryStore, ProvenanceLinker
from hermes_prime.memory.backends.sqlite_backend import SQLiteMemoryBackend
from hermes_prime.memory.base import MemorySearchResult
from hermes_prime.signing import HMACSigner
from hermes_prime.utils import new_urn_uuid, utc_now_iso


def _make_intent_root(scope: str = "/test") -> IntentRoot:
    signer = HMACSigner(identity="test", secret=b"test-secret")
    ir = IntentRoot(
        intent_root=new_urn_uuid(),
        scope=scope,
        issued_to="test-user",
        issued_at=utc_now_iso(),
        expires_at="2099-12-31T23:59:59Z",
        signature="sig:placeholder",
    )
    payload = f"{ir.intent_root}:{ir.scope}:{ir.issued_to}:{ir.issued_at}:{ir.expires_at}"
    sig = signer.sign(payload.encode("utf-8"))
    object.__setattr__(ir, "signature", sig)
    return ir


class TestSQLiteMemoryBackend(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "test_memory.db"
        self.backend = SQLiteMemoryBackend(self.db_path)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_claim(self, fact_id: str | None = None, claim_text: str = "test fact") -> MemoryClaim:
        return MemoryClaim(
            fact_id=fact_id or new_urn_uuid(),
            claim=claim_text,
            source={"source": "test"},
            epistemic_confidence=0.8,
            verification_status="unverified",
            source_trust="test",
            timestamp=utc_now_iso(),
            trust_state=TrustState.UNVERIFIED,
            tier=MemoryTier.QUARANTINE,
            contradictions=[],
            intent_root=new_urn_uuid(),
        )

    def test_store_and_retrieve(self):
        claim = self._make_claim()
        self.backend.store(claim)
        retrieved = self.backend.get(claim.fact_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.claim, "test fact")
        self.assertEqual(retrieved.trust_state, TrustState.UNVERIFIED)

    def test_store_overwrite(self):
        fid = new_urn_uuid()
        c1 = self._make_claim(fid, "version 1")
        self.backend.store(c1)
        c2 = self._make_claim(fid, "version 2")
        self.backend.store(c2)
        retrieved = self.backend.get(fid)
        self.assertEqual(retrieved.claim, "version 2")

    def test_get_missing(self):
        result = self.backend.get(new_urn_uuid())
        self.assertIsNone(result)

    def test_search_found(self):
        self.backend.store(self._make_claim(claim_text="the quick brown fox"))
        self.backend.store(self._make_claim(claim_text="jumps over the lazy dog"))
        results = self.backend.search("quick", limit=10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].claim, "the quick brown fox")

    def test_search_not_found(self):
        self.backend.store(self._make_claim(claim_text="hello world"))
        results = self.backend.search("nonexistent", limit=10)
        self.assertEqual(len(results), 0)

    def test_list_all(self):
        self.backend.store(self._make_claim())
        self.backend.store(self._make_claim())
        claims = self.backend.list_all()
        self.assertEqual(len(claims), 2)

    def test_delete(self):
        claim = self._make_claim()
        self.backend.store(claim)
        self.assertTrue(self.backend.delete(claim.fact_id))
        self.assertIsNone(self.backend.get(claim.fact_id))

    def test_delete_missing(self):
        self.assertFalse(self.backend.delete(new_urn_uuid()))

    def test_count(self):
        self.assertEqual(self.backend.count(), 0)
        self.backend.store(self._make_claim())
        self.assertEqual(self.backend.count(), 1)
        self.backend.store(self._make_claim())
        self.assertEqual(self.backend.count(), 2)

    def test_gc(self):
        self.backend.store(self._make_claim(claim_text="old"))
        self.backend.store(self._make_claim(claim_text="new"))
        deleted = self.backend.gc("2099-01-01T00:00:00Z")
        self.assertGreaterEqual(deleted, 0)

    def test_search_result_from_claim(self):
        claim = self._make_claim()
        sr = MemorySearchResult.from_claim(claim, similarity=0.95)
        self.assertEqual(sr.fact_id, claim.fact_id)
        self.assertEqual(sr.claim, claim.claim)
        self.assertEqual(sr.similarity, 0.95)


class TestMemoryStore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "memory.db"
        self.backend = SQLiteMemoryBackend(self.db_path)
        self.store = MemoryStore(
            backend=self.backend,
            depth_policy=DepthPolicy(max_claims_per_intent=10, max_total_claims=100),
        )
        self.intent = _make_intent_root()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_and_recall(self):
        result = self.store.write(
            claim_text="hermes prime is governed",
            source={"source": "test"},
            intent_root=self.intent,
            epistemic_confidence=0.9,
            source_trust="verified",
        )
        self.assertTrue(result.success)
        self.assertIsNotNone(result.fact_id)
        self.assertIsNotNone(result.attestation)
        self.assertEqual(result.attestation.intent_root, self.intent.intent_root)

        recall = self.store.recall("governed", limit=10)
        self.assertGreaterEqual(len(recall.results), 1)
        self.assertIn("governed", recall.results[0].claim.lower())

    def test_write_depth_limit_enforced(self):
        tight_store = MemoryStore(
            backend=self.backend,
            depth_policy=DepthPolicy(max_claims_per_intent=2, max_total_claims=100),
        )
        self.assertTrue(tight_store.write("fact 1", {"s": "t"}, self.intent).success)
        self.assertTrue(tight_store.write("fact 2", {"s": "t"}, self.intent).success)
        result = tight_store.write("fact 3", {"s": "t"}, self.intent)
        self.assertFalse(result.success)
        self.assertIn("max claims", result.error.lower())

    def test_get_by_fact_id(self):
        write = self.store.write("unique fact", {"s": "t"}, self.intent)
        result = self.store.get(write.fact_id)
        self.assertTrue(result.success)
        self.assertEqual(result.claim.claim, "unique fact")

    def test_get_missing(self):
        result = self.store.get(new_urn_uuid())
        self.assertFalse(result.success)
        self.assertIn("not found", result.error)

    def test_list_all(self):
        self.store.write("a", {"s": "t"}, self.intent)
        self.store.write("b", {"s": "t"}, self.intent)
        result = self.store.list_all()
        self.assertEqual(result.total_count, 2)

    def test_revoke(self):
        write = self.store.write("revocable", {"s": "t"}, self.intent)
        result = self.store.revoke(write.fact_id)
        self.assertTrue(result.success)
        claim = self.backend.get(write.fact_id)
        self.assertEqual(claim.trust_state, TrustState.REVOKED)

    def test_revoke_missing(self):
        result = self.store.revoke(new_urn_uuid())
        self.assertFalse(result.success)

    def test_promote(self):
        write = self.store.write("promotable", {"s": "t"}, self.intent)
        result = self.store.promote(write.fact_id, TrustState.OBSERVED)
        self.assertTrue(result.success)
        claim = self.backend.get(write.fact_id)
        self.assertEqual(claim.trust_state, TrustState.OBSERVED)

    def test_promote_full_chain(self):
        write = self.store.write("chain", {"s": "t"}, self.intent, epistemic_confidence=0.9)
        self.assertTrue(self.store.promote(write.fact_id, TrustState.OBSERVED).success)
        self.assertTrue(self.store.promote(write.fact_id, TrustState.ATTESTED).success)
        self.assertTrue(self.store.promote(write.fact_id, TrustState.VALIDATED).success)
        self.assertTrue(self.store.promote(write.fact_id, TrustState.EXECUTABLE).success)
        claim = self.backend.get(write.fact_id)
        self.assertEqual(claim.trust_state, TrustState.EXECUTABLE)

    def test_promote_invalid_transition(self):
        write = self.store.write("bad promote", {"s": "t"}, self.intent)
        result = self.store.promote(write.fact_id, TrustState.REVOKED)
        self.assertFalse(result.success)

    def test_promote_with_contradictions_blocked(self):
        claim = MemoryClaim(
            fact_id=new_urn_uuid(),
            claim="contradictory",
            source={"s": "t"},
            epistemic_confidence=0.9,
            verification_status="unverified",
            source_trust="test",
            timestamp=utc_now_iso(),
            trust_state=TrustState.UNVERIFIED,
            tier=MemoryTier.QUARANTINE,
            contradictions=[{"fact_id": new_urn_uuid(), "reason": "conflict"}],
            intent_root=self.intent.intent_root,
        )
        self.backend.store(claim)
        self.store.promote(claim.fact_id, TrustState.OBSERVED)
        self.store.promote(claim.fact_id, TrustState.ATTESTED)
        result = self.store.promote(claim.fact_id, TrustState.VALIDATED)
        self.assertFalse(result.success)

    def test_gc(self):
        self.store.write("keep", {"s": "t"}, self.intent)
        result = self.store.gc(before_timestamp="2099-01-01T00:00:00Z")
        self.assertTrue(result.success)

    def test_attestation_created(self):
        result = self.store.write("attested fact", {"s": "t"}, self.intent)
        self.assertIsNotNone(result.attestation)
        self.assertEqual(result.attestation.fact_id, result.fact_id)
        self.assertEqual(result.attestation.intent_root, self.intent.intent_root)
        self.assertTrue(result.attestation.signature.startswith("sig:hmac-sha256"))


class TestProvenanceLinker(unittest.TestCase):
    def setUp(self):
        self.linker = ProvenanceLinker()
        self.intent = _make_intent_root()

    def test_build_claim_defaults_to_quarantine(self):
        claim = self.linker.build_claim(
            claim_text="test belief",
            source={"source": "unit-test"},
            intent_root=self.intent,
        )
        self.assertEqual(claim.tier, MemoryTier.QUARANTINE)
        self.assertEqual(claim.trust_state, TrustState.UNVERIFIED)
        self.assertEqual(claim.intent_root, self.intent.intent_root)
        self.assertTrue(claim.fact_id.startswith("urn:uuid:"))

    def test_attest_memory_creates_signed_attestation(self):
        claim = self.linker.build_claim("signed belief", {"s": "t"}, self.intent)
        att = self.linker.attest_memory(claim, self.intent)
        self.assertTrue(att.signature.startswith("sig:hmac-sha256"))
        self.assertEqual(att.fact_id, claim.fact_id)
        self.assertEqual(att.intent_root, self.intent.intent_root)

    def test_verify_attestation(self):
        claim = self.linker.build_claim("verifiable", {"s": "t"}, self.intent)
        att = self.linker.attest_memory(claim, self.intent)
        self.assertTrue(self.linker.verify_attestation(att, self.intent))

    def test_verify_attestation_tampered(self):
        claim = self.linker.build_claim("tampered", {"s": "t"}, self.intent)
        att = self.linker.attest_memory(claim, self.intent)
        att.claim_hash = "tampered_hash"
        self.assertFalse(self.linker.verify_attestation(att, self.intent))

    def test_intent_root_mismatch_raises(self):
        claim = self.linker.build_claim("mismatch", {"s": "t"}, self.intent)
        other_intent = _make_intent_root()
        with self.assertRaises(ValueError):
            self.linker.attest_memory(claim, other_intent)


class TestDepthPolicy(unittest.TestCase):
    def setUp(self):
        self.policy = DepthPolicy(
            max_claims_per_intent=5,
            max_total_claims=50,
            max_claim_length=100,
        )

    def test_allows_within_limits(self):
        allowed, reason = self.policy.check_claim_allowed("short claim", 3, 10)
        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    def test_blocks_excessive_length(self):
        long_claim = "x" * 200
        allowed, reason = self.policy.check_claim_allowed(long_claim, 0, 0)
        self.assertFalse(allowed)
        self.assertIn("max length", reason.lower())

    def test_blocks_per_intent_excess(self):
        allowed, reason = self.policy.check_claim_allowed("ok", 5, 10)
        self.assertFalse(allowed)
        self.assertIn("max claims", reason.lower())

    def test_blocks_total_excess(self):
        allowed, reason = self.policy.check_claim_allowed("ok", 0, 50)
        self.assertFalse(allowed)
        self.assertIn("total claims", reason.lower())

    def test_to_dict(self):
        d = self.policy.to_dict()
        self.assertEqual(d["max_claims_per_intent"], 5)
        self.assertEqual(d["max_claim_length"], 100)


class TestMemorySearchResult(unittest.TestCase):
    def test_from_claim(self):
        claim = MemoryClaim(
            fact_id=new_urn_uuid(),
            claim="searchable fact",
            source={"src": "test"},
            epistemic_confidence=0.75,
            verification_status="unverified",
            source_trust="high",
            timestamp=utc_now_iso(),
            trust_state=TrustState.UNVERIFIED,
            tier=MemoryTier.QUARANTINE,
            contradictions=[{"id": "abc"}],
            intent_root=new_urn_uuid(),
        )
        sr = MemorySearchResult.from_claim(claim, similarity=0.88)
        self.assertEqual(sr.fact_id, claim.fact_id)
        self.assertEqual(sr.claim, "searchable fact")
        self.assertEqual(sr.epistemic_confidence, 0.75)
        self.assertEqual(sr.similarity, 0.88)
        self.assertEqual(len(sr.contradictions), 1)


if __name__ == "__main__":
    unittest.main()
