from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from hermes_prime.contracts import MemoryClaim, MemoryTier, TrustState
from hermes_prime.memory.backends.mem0_backend import Mem0Backend, _extract_entities
from hermes_prime.utils import new_urn_uuid, utc_now_iso


def _make_claim(
    fact_id: str | None = None,
    claim_text: str = "Alice worked on a machine learning project called ProjectX",
    memory_type: str = "episodic",
    trust_state: TrustState = TrustState.UNVERIFIED,
    intent_root: str = "",
) -> MemoryClaim:
    return MemoryClaim(
        fact_id=fact_id or new_urn_uuid(),
        claim=claim_text,
        source={"agent": "test_agent", "memory_type": memory_type},
        epistemic_confidence=0.5,
        verification_status="unverified",
        source_trust="observed",
        timestamp=utc_now_iso(),
        trust_state=trust_state,
        tier=MemoryTier.QUARANTINE,
        contradictions=[],
        intent_root=intent_root,
    )


class TestEntityExtraction(unittest.TestCase):
    def test_quoted_entities(self):
        entities = _extract_entities('Bob said "this is a test"')
        types = [t for _, t in entities]
        self.assertIn("QUOTED", types)
        texts = [t for t, _ in entities]
        self.assertTrue(any("this is a test" in t for t in texts))

    def test_proper_nouns(self):
        entities = _extract_entities("Alice Johnson worked at Google")
        texts = [t for t, _ in entities]
        self.assertTrue(any("Alice Johnson" in t for t in texts))

    def test_compound_nouns(self):
        entities = _extract_entities("We used machine learning for the project")
        texts = [t.lower() for t, _ in entities]
        self.assertTrue(any("machine learning" in t for t in texts))

    def test_single_nouns(self):
        entities = _extract_entities("Alice met with Charlie about the Django project")
        texts = [t for t, _ in entities]
        self.assertIn("Alice", texts)
        self.assertIn("Charlie", texts)
        self.assertIn("Django", texts)

    def test_skip_generic_words(self):
        entities = _extract_entities("The project is about This and That")
        texts = [t for t, _ in entities]
        for skip in ("The", "This", "That"):
            self.assertNotIn(skip, texts)

    def test_empty_text(self):
        entities = _extract_entities("")
        self.assertEqual(entities, [])

    def test_no_entities(self):
        entities = _extract_entities("it was a nice day")
        types = [t for _, t in entities]
        self.assertTrue(all(t != "PROPER" for t in types))

    def test_multiple_entity_types(self):
        text = '"smart assistant" uses machine learning'
        entities = _extract_entities(text)
        types = {t for _, t in entities}
        self.assertIn("QUOTED", types)
        self.assertIn("COMPOUND", types)

    def test_deduplication(self):
        text = "Alice and Alice worked on machine learning and machine learning"
        entities = _extract_entities(text)
        texts = [t.lower() for t, _ in entities]
        self.assertEqual(texts.count("alice"), 1)


@unittest.skipUnless(
    importlib.util.find_spec("chromadb") is not None,
    "chromadb not installed",
)
class TestMem0Backend(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.chroma_path = self.tmp / "chroma"
        self.backend = Mem0Backend(chroma_path=self.chroma_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_store_and_get(self):
        claim = _make_claim()
        self.backend.store(claim)
        retrieved = self.backend.get(claim.fact_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.fact_id, claim.fact_id)
        self.assertEqual(retrieved.claim, claim.claim)

    def test_get_nonexistent(self):
        retrieved = self.backend.get("nonexistent")
        self.assertIsNone(retrieved)

    def test_search(self):
        c1 = _make_claim(claim_text="Alice works on machine learning models")
        c2 = _make_claim(claim_text="Bob prefers classical music")
        self.backend.store(c1)
        self.backend.store(c2)
        results = self.backend.search("machine learning", limit=5)
        self.assertGreaterEqual(len(results), 1)
        result_ids = {r.fact_id for r in results}
        self.assertIn(c1.fact_id, result_ids)

    def test_search_empty_backend(self):
        results = self.backend.search("test", limit=5)
        self.assertEqual(results, [])

    def test_list_all(self):
        c1 = _make_claim(claim_text="First claim")
        c2 = _make_claim(claim_text="Second claim")
        self.backend.store(c1)
        self.backend.store(c2)
        claims = self.backend.list_all()
        self.assertEqual(len(claims), 2)
        ids = {c.fact_id for c in claims}
        self.assertIn(c1.fact_id, ids)
        self.assertIn(c2.fact_id, ids)

    def test_list_all_empty(self):
        claims = self.backend.list_all()
        self.assertEqual(claims, [])

    def test_delete(self):
        claim = _make_claim()
        self.backend.store(claim)
        self.assertTrue(self.backend.delete(claim.fact_id))
        self.assertIsNone(self.backend.get(claim.fact_id))

    def test_delete_nonexistent(self):
        self.assertFalse(self.backend.delete("nonexistent"))

    def test_count(self):
        self.assertEqual(self.backend.count(), 0)
        self.backend.store(_make_claim(claim_text="A"))
        self.backend.store(_make_claim(claim_text="B"))
        self.assertEqual(self.backend.count(), 2)

    def test_gc(self):
        old = utc_now_iso()
        c1 = _make_claim(claim_text="Old claim", trust_state=TrustState.UNVERIFIED)
        import datetime as dt
        c1.timestamp = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=10)).isoformat().replace("+00:00", "Z")
        c2 = _make_claim(claim_text="Fresh claim")
        self.backend.store(c1)
        self.backend.store(c2)
        deleted = self.backend.gc(old)
        self.assertEqual(deleted, 1)
        self.assertIsNone(self.backend.get(c1.fact_id))
        self.assertIsNotNone(self.backend.get(c2.fact_id))

    def test_gc_empty_backend(self):
        result = self.backend.gc(utc_now_iso())
        self.assertEqual(result, 0)

    def test_entity_boost_in_search(self):
        c1 = _make_claim(claim_text="Alice is an expert in machine learning and AI")
        c2 = _make_claim(claim_text="Python is a programming language")
        self.backend.store(c1)
        self.backend.store(c2)
        results = self.backend.search("Alice machine learning", limit=5)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].fact_id, c1.fact_id)

    def test_entity_linking_on_store(self):
        claim = _make_claim(claim_text="Alice and Bob worked on deep learning")
        self.backend.store(claim)
        entities = _extract_entities(claim.claim)
        self.assertGreater(len(entities), 0)

    def test_delete_cleans_up_entity_links(self):
        claim = _make_claim(claim_text="Alice worked on machine learning")
        self.backend.store(claim)
        self.backend.delete(claim.fact_id)
        results = self.backend.search("Alice", limit=5)
        self.assertNotIn(claim.fact_id, {r.fact_id for r in results})

    def test_store_updates_existing(self):
        claim = _make_claim(claim_text="Original text")
        self.backend.store(claim)
        claim.claim = "Updated text"
        self.backend.store(claim)
        retrieved = self.backend.get(claim.fact_id)
        self.assertEqual(retrieved.claim, "Updated text")

    def test_count_after_delete(self):
        c1 = _make_claim(claim_text="C1")
        c2 = _make_claim(claim_text="C2")
        c3 = _make_claim(claim_text="C3")
        self.backend.store(c1)
        self.backend.store(c2)
        self.backend.store(c3)
        self.backend.delete(c2.fact_id)
        self.assertEqual(self.backend.count(), 2)

    def test_gc_respects_cutoff(self):
        past = "2020-01-01T00:00:00Z"
        recent = _make_claim(claim_text="Recent claim")
        self.backend.store(recent)
        deleted = self.backend.gc(past)
        self.assertEqual(deleted, 0)
        self.assertIsNotNone(self.backend.get(recent.fact_id))

    def test_search_limit(self):
        for i in range(5):
            self.backend.store(_make_claim(claim_text=f"Claim number {i}"))
        results = self.backend.search("Claim", limit=3)
        self.assertLessEqual(len(results), 3)


if __name__ == "__main__":
    unittest.main()
