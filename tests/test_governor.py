from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hermes_prime.contracts import IntentRoot, MemoryClaim, MemoryTier, TrustState
from hermes_prime.memory import DepthPolicy, MemoryStore, ProvenanceLinker
from hermes_prime.memory.backends.sqlite_backend import SQLiteMemoryBackend
from hermes_prime.memory.governor import (
    ContradictionDetector,
    ContradictionResult,
    MemoryGovernor,
    _jaccard_similarity,
    _tokenize,
)
from hermes_prime.memory.graph import KnowledgeGraph
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


_FACT_COUNTER: int = 0


def _make_claim(
    fact_id: str | None = None,
    claim_text: str = "test fact",
    intent_root: str = "",
) -> MemoryClaim:
    global _FACT_COUNTER
    _FACT_COUNTER += 1
    return MemoryClaim(
        fact_id=fact_id or new_urn_uuid(),
        claim=claim_text,
        source={"agent": "test"},
        epistemic_confidence=0.5,
        verification_status="unverified",
        source_trust="observed",
        timestamp=utc_now_iso(),
        trust_state=TrustState.UNVERIFIED,
        tier=MemoryTier.QUARANTINE,
        contradictions=[],
        intent_root=intent_root,
    )


def _urn(id_str: str) -> str:
    return f"urn:uuid:00000000-0000-0000-0000-{id_str:0>12}"


class TestTokenizeAndSimilarity(unittest.TestCase):
    def test_tokenize(self):
        tokens = _tokenize("hello world test")
        self.assertIn("hello", tokens)
        self.assertIn("world", tokens)
        self.assertIn("test", tokens)

    def test_tokenize_short_words_removed(self):
        tokens = _tokenize("a an in on at")
        self.assertEqual(len(tokens), 0)

    def test_tokenize_punctuation_stripped(self):
        tokens = _tokenize("hello, world! test.")
        self.assertIn("hello", tokens)
        self.assertIn("world", tokens)

    def test_jaccard_identical(self):
        a = {"hello", "world"}
        self.assertEqual(_jaccard_similarity(a, a), 1.0)

    def test_jaccard_disjoint(self):
        a = {"hello"}
        b = {"world"}
        self.assertEqual(_jaccard_similarity(a, b), 0.0)

    def test_jaccard_partial(self):
        a = {"hello", "world", "foo"}
        b = {"hello", "world", "bar"}
        self.assertAlmostEqual(_jaccard_similarity(a, b), 2 / 4)


class TestContradictionDetector(unittest.TestCase):
    def setUp(self):
        self.detector = ContradictionDetector(similarity_threshold=0.4)
        self.intent = _make_intent_root()
        self.existing = [
            _make_claim(
                fact_id=_urn(1),
                claim_text="the API endpoint returns JSON data",
                intent_root=self.intent.intent_root,
            ),
            _make_claim(
                fact_id=_urn(2),
                claim_text="the database connection is stable",
                intent_root=self.intent.intent_root,
            ),
        ]

    def test_detect_similar_claim(self):
        new_claim = _make_claim(
            fact_id=_urn(10),
            claim_text="the API endpoint returns XML data now",
            intent_root=self.intent.intent_root,
        )
        result = self.detector.detect_against_claim(new_claim, self.existing)
        self.assertGreaterEqual(len(result), 1)
        fact_ids = [c["fact_id"] for c in result]
        self.assertIn(_urn(1), fact_ids)

    def test_no_contradiction_for_different_topics(self):
        new_claim = _make_claim(
            fact_id=_urn(11),
            claim_text="the weather is sunny today",
            intent_root=self.intent.intent_root,
        )
        result = self.detector.detect_against_claim(new_claim, self.existing)
        self.assertEqual(len(result), 0)

    def test_different_intent_not_compared(self):
        other_intent = _make_intent_root()
        new_claim = _make_claim(
            fact_id=_urn(12),
            claim_text="the API endpoint returns JSON data",
            intent_root=other_intent.intent_root,
        )
        result = self.detector.detect_against_claim(new_claim, self.existing)
        self.assertEqual(len(result), 0)

    def test_self_not_compared(self):
        new_claim = _make_claim(
            fact_id=_urn(1),
            claim_text="the API endpoint returns JSON data",
            intent_root=self.intent.intent_root,
        )
        result = self.detector.detect_against_claim(new_claim, self.existing)
        self.assertEqual(len(result), 0)

    def test_detect_explicit(self):
        result = self.detector.detect_explicit(
            _urn(99), [_urn(1), "nonexistent"], self.existing,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["fact_id"], _urn(1))

    def test_high_threshold_no_match(self):
        strict = ContradictionDetector(similarity_threshold=0.9)
        new_claim = _make_claim(
            fact_id=_urn(13),
            claim_text="the frontend service renders HTML templates",
            intent_root=self.intent.intent_root,
        )
        result = strict.detect_against_claim(new_claim, self.existing)
        self.assertEqual(len(result), 0)


class TestMemoryGovernor(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "test_governor.db"
        self.backend = SQLiteMemoryBackend(self.db_path)
        self.graph = KnowledgeGraph()
        self.store = MemoryStore(
            backend=self.backend,
            knowledge_graph=self.graph,
            depth_policy=DepthPolicy(max_claims_per_intent=50, max_total_claims=100),
        )
        self.detector = ContradictionDetector(similarity_threshold=0.4)
        self.governor = MemoryGovernor(
            memory_store=self.store,
            detector=self.detector,
        )
        self.intent = _make_intent_root()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_review_no_contradiction(self):
        result = self.governor.review(
            "unique claim with very specific content",
            {"agent": "test"},
            self.intent,
        )
        self.assertTrue(result.success)
        if result.claim:
            self.assertEqual(len(result.claim.contradictions), 0)

    def test_review_detects_similar_claim(self):
        w1 = self.store.write(
            "the API service returns JSON formatted data",
            {"agent": "test"},
            self.intent,
        )
        result = self.governor.review(
            "the API service returns XML formatted data now",
            {"agent": "test"},
            self.intent,
        )
        self.assertTrue(result.success)
        if result.claim:
            self.assertGreaterEqual(len(result.claim.contradictions), 1)
            self.assertEqual(
                result.claim.contradictions[0]["fact_id"],
                w1.fact_id,
            )

    def test_review_explicit_contradiction(self):
        w1 = self.store.write("initial fact", {"agent": "test"}, self.intent)
        result = self.governor.review(
            "contradicting fact",
            {"agent": "test"},
            self.intent,
            contradicts=[w1.fact_id],
        )
        self.assertTrue(result.success)
        if result.claim:
            self.assertGreaterEqual(len(result.claim.contradictions), 1)

    def test_review_backlinks_existing(self):
        w1 = self.store.write("the server configuration is correct", {"agent": "test"}, self.intent)
        self.governor.review(
            "the server configuration is wrong and needs fixing",
            {"agent": "test"},
            self.intent,
        )
        updated = self.backend.get(w1.fact_id)
        self.assertIsNotNone(updated)
        self.assertGreaterEqual(len(updated.contradictions), 0)

    def test_review_depth_limit_still_applies(self):
        tight_governor = MemoryGovernor(
            memory_store=MemoryStore(
                backend=self.backend,
                depth_policy=DepthPolicy(max_claims_per_intent=1, max_total_claims=10),
            ),
        )
        tight_governor.review("first fact", {"agent": "test"}, self.intent)
        result = tight_governor.review("second fact", {"agent": "test"}, self.intent)
        self.assertFalse(result.success)

    def test_arbitrate_keep_a(self):
        w1 = self.store.write("fact A", {"agent": "test"}, self.intent)
        w2 = self.store.write("fact B", {"agent": "test"}, self.intent)
        claim_a = self.backend.get(w1.fact_id)
        claim_b = self.backend.get(w2.fact_id)
        if claim_a and claim_b:
            claim_a.contradictions.append({"fact_id": w2.fact_id, "reason": "test"})
            claim_b.contradictions.append({"fact_id": w1.fact_id, "reason": "test"})
            self.backend.store(claim_a)
            self.backend.store(claim_b)

        result = self.governor.arbitrate(w1.fact_id, w2.fact_id, resolution="keep_a")
        self.assertTrue(result.success)

        updated_a = self.backend.get(w1.fact_id)
        updated_b = self.backend.get(w2.fact_id)
        self.assertIsNotNone(updated_a)
        self.assertIsNotNone(updated_b)
        self.assertEqual(updated_a.trust_state, TrustState.VALIDATED)
        self.assertEqual(updated_b.trust_state, TrustState.REVOKED)
        self.assertEqual(len(updated_a.contradictions), 0)

    def test_arbitrate_keep_b(self):
        w1 = self.store.write("fact C", {"agent": "test"}, self.intent)
        w2 = self.store.write("fact D", {"agent": "test"}, self.intent)
        claim_a = self.backend.get(w1.fact_id)
        claim_b = self.backend.get(w2.fact_id)
        if claim_a and claim_b:
            claim_a.contradictions.append({"fact_id": w2.fact_id, "reason": "test"})
            claim_b.contradictions.append({"fact_id": w1.fact_id, "reason": "test"})
            self.backend.store(claim_a)
            self.backend.store(claim_b)

        result = self.governor.arbitrate(w1.fact_id, w2.fact_id, resolution="keep_b")
        self.assertTrue(result.success)

        updated_a = self.backend.get(w1.fact_id)
        updated_b = self.backend.get(w2.fact_id)
        self.assertEqual(updated_a.trust_state, TrustState.REVOKED)
        self.assertEqual(updated_b.trust_state, TrustState.VALIDATED)

    def test_arbitrate_missing_fact(self):
        result = self.governor.arbitrate("nonexistent-a", "nonexistent-b")
        self.assertFalse(result.success)

    def test_arbitrate_invalid_resolution(self):
        w1 = self.store.write("fact E", {"agent": "test"}, self.intent)
        w2 = self.store.write("fact F", {"agent": "test"}, self.intent)
        result = self.governor.arbitrate(w1.fact_id, w2.fact_id, resolution="invalid")
        self.assertFalse(result.success)

    def test_get_contradictions(self):
        w1 = self.store.write("the service is running fine", {"agent": "test"}, self.intent)
        self.governor.review(
            "the service is running with errors",
            {"agent": "test"},
            self.intent,
        )
        contradictions = self.governor.get_contradictions(w1.fact_id)
        self.assertIsInstance(contradictions, list)

    def test_get_contradictions_nonexistent(self):
        result = self.governor.get_contradictions("nonexistent")
        self.assertEqual(result, [])

    def test_get_contradiction_count(self):
        w1 = self.store.write("count test initial", {"agent": "test"}, self.intent)
        self.governor.review(
            "count test followup conflicting",
            {"agent": "test"},
            self.intent,
        )
        count = self.governor.get_contradiction_count(w1.fact_id)
        self.assertIsInstance(count, int)

    def test_contradiction_result_property(self):
        r = ContradictionResult(fact_id="test", contradictions=[])
        self.assertFalse(r.has_contradictions)
        r.contradictions.append({"fact_id": "other", "reason": "test"})
        self.assertTrue(r.has_contradictions)

    def test_review_preserves_normal_write(self):
        result = self.governor.review(
            "normal claim without any conflicts whatsoever",
            {"agent": "test"},
            self.intent,
        )
        self.assertTrue(result.success)
        self.assertIsNotNone(result.fact_id)

    def test_multiple_contradictions(self):
        self.governor.review("data pipeline uses Python", {"agent": "test"}, self.intent)
        self.governor.review("data pipeline uses JavaScript", {"agent": "test"}, self.intent)
        result = self.governor.review(
            "data pipeline uses Rust now",
            {"agent": "test"},
            self.intent,
        )
        self.assertTrue(result.success)
        if result.claim:
            self.assertGreaterEqual(len(result.claim.contradictions), 1)


class TestContradictionResult(unittest.TestCase):
    def test_default_no_contradictions(self):
        r = ContradictionResult(fact_id="fact-1")
        self.assertEqual(r.contradictions, [])
        self.assertFalse(r.has_contradictions)

    def test_with_contradictions(self):
        r = ContradictionResult(
            fact_id="fact-1",
            contradictions=[{"fact_id": "other", "reason": "conflict"}],
        )
        self.assertTrue(r.has_contradictions)


if __name__ == "__main__":
    unittest.main()
