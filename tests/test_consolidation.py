from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hermes_prime.contracts import IntentRoot
from hermes_prime.memory import DepthPolicy, MemoryStore
from hermes_prime.memory.backends.sqlite_backend import SQLiteMemoryBackend
from hermes_prime.memory.consolidation import (
    ConsolidationRequest,
    ConsolidationResult,
    PatternResult,
    ReflectiveConsolidator,
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


class TestReflectiveConsolidator(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "test_consolidation.db"
        self.backend = SQLiteMemoryBackend(self.db_path)
        self.graph = KnowledgeGraph()
        self.store = MemoryStore(
            backend=self.backend,
            knowledge_graph=self.graph,
            depth_policy=DepthPolicy(max_claims_per_intent=50, max_total_claims=100),
        )
        self.consolidator = ReflectiveConsolidator(memory_store=self.store)
        self.intent = _make_intent_root()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_sources(self, count: int = 3) -> list[str]:
        fact_ids: list[str] = []
        for i in range(count):
            r = self.store.write(
                f"source observation {i}: step in the task",
                {"agent": "test-agent"},
                self.intent,
                epistemic_confidence=0.7,
            )
            fact_ids.append(r.fact_id)
        return fact_ids

    def test_consolidate_creates_reflective_memory(self):
        self._write_sources(2)
        request = ConsolidationRequest(
            intent_root=self.intent,
            summary="Task completed: all steps executed successfully. Key decision was to use approach X.",
        )
        result = self.consolidator.consolidate(request)
        self.assertTrue(result.success)
        self.assertNotEqual(result.reflective_fact_id, "")
        self.assertEqual(result.source_count, 2)

    def test_consolidate_reflective_linked_via_causal_parent(self):
        source_ids = self._write_sources(3)
        request = ConsolidationRequest(intent_root=self.intent, summary="consolidated summary")
        result = self.consolidator.consolidate(request)
        self.assertTrue(result.success)

        lineage = self.graph.get_lineage(result.reflective_fact_id)
        self.assertGreaterEqual(len(lineage), 1)
        self.assertEqual(lineage[0], source_ids[-1])

    def test_consolidate_with_patterns(self):
        self._write_sources(2)
        request = ConsolidationRequest(
            intent_root=self.intent,
            summary="Task summary",
            patterns=[
                {
                    "text": "Pattern: API calls should use retry with exponential backoff",
                    "type": "operational",
                },
                {
                    "text": "Pattern: Database migrations should be tested in staging first",
                    "type": "operational",
                },
            ],
        )
        result = self.consolidator.consolidate(request)
        self.assertTrue(result.success)
        self.assertEqual(len(result.patterns), 2)
        for p in result.patterns:
            self.assertIsInstance(p, PatternResult)
            self.assertNotEqual(p.fact_id, "")
            self.assertIn("text", p.pattern)

    def test_consolidate_with_source_filter(self):
        source_ids = self._write_sources(4)
        filtered = source_ids[:2]
        request = ConsolidationRequest(
            intent_root=self.intent,
            summary="Filtered summary",
            source_fact_ids=filtered,
        )
        result = self.consolidator.consolidate(request)
        self.assertTrue(result.success)
        self.assertEqual(result.source_count, 2)

    def test_get_consolidations_returns_reflective_memories(self):
        self._write_sources(2)
        request = ConsolidationRequest(intent_root=self.intent, summary="summary for retrieval")
        self.consolidator.consolidate(request)

        consolidations = self.consolidator.get_consolidations(self.intent.intent_root)
        self.assertGreaterEqual(len(consolidations), 1)
        for c in consolidations:
            self.assertEqual(c.source.get("memory_type"), "reflective")

    def test_get_consolidations_empty(self):
        result = self.consolidator.get_consolidations("nonexistent-intent")
        self.assertEqual(result, [])

    def test_get_patterns_returns_strategic_memories(self):
        self._write_sources(1)
        request = ConsolidationRequest(
            intent_root=self.intent,
            summary="summary",
            patterns=[{"text": "Strategic insight", "type": "operational"}],
        )
        self.consolidator.consolidate(request)

        patterns = self.consolidator.get_patterns(self.intent.intent_root)
        self.assertGreaterEqual(len(patterns), 1)
        for p in patterns:
            self.assertEqual(p.source.get("memory_type"), "strategic")

    def test_get_patterns_empty(self):
        result = self.consolidator.get_patterns("nonexistent-intent")
        self.assertEqual(result, [])

    def test_get_reflective_lineage(self):
        source_ids = self._write_sources(2)
        request = ConsolidationRequest(intent_root=self.intent, summary="lineage test")
        result = self.consolidator.consolidate(request)

        lineage = self.consolidator.get_reflective_lineage(result.reflective_fact_id)
        self.assertGreaterEqual(len(lineage), 1)
        self.assertEqual(lineage[0]["fact_id"], source_ids[-1])

    def test_get_reflective_lineage_no_lineage(self):
        result = self.consolidator.get_reflective_lineage("nonexistent")
        self.assertEqual(result, [])

    def test_consolidate_no_sources(self):
        request = ConsolidationRequest(
            intent_root=_make_intent_root(),
            summary="orphan consolidation",
        )
        result = self.consolidator.consolidate(request)
        self.assertTrue(result.success)
        self.assertEqual(result.source_count, 0)
        self.assertNotEqual(result.reflective_fact_id, "")

    def test_consolidate_depth_limit_respected(self):
        tight_store = MemoryStore(
            backend=self.backend,
            depth_policy=DepthPolicy(max_claims_per_intent=1, max_total_claims=5),
        )
        tight_consolidator = ReflectiveConsolidator(memory_store=tight_store)
        self._write_sources(2)

        request = ConsolidationRequest(
            intent_root=self.intent,
            summary="this should fail due to depth",
        )
        result = tight_consolidator.consolidate(request)
        self.assertFalse(result.success)

    def test_pattern_links_to_reflective_when_no_source_ids(self):
        self._write_sources(1)
        request = ConsolidationRequest(
            intent_root=self.intent,
            summary="summary",
            patterns=[{"text": "pattern without explicit sources", "type": "strategic"}],
        )
        result = self.consolidator.consolidate(request)
        self.assertTrue(result.success)
        self.assertEqual(len(result.patterns), 1)

        pattern_lineage = self.graph.get_lineage(result.patterns[0].fact_id)
        self.assertGreaterEqual(len(pattern_lineage), 1)

    def test_consolidation_result_defaults(self):
        r = ConsolidationResult(success=True, intent_root="test")
        self.assertEqual(r.reflective_fact_id, "")
        self.assertEqual(r.source_count, 0)
        self.assertEqual(r.patterns, [])
        self.assertEqual(r.error, "")

    def test_pattern_result_dataclass(self):
        p = PatternResult(fact_id="fact-1", pattern={"text": "test"})
        self.assertEqual(p.fact_id, "fact-1")
        self.assertEqual(p.pattern["text"], "test")

    def test_consolidation_request_defaults(self):
        r = ConsolidationRequest(intent_root=self.intent, summary="test")
        self.assertEqual(r.patterns, [])
        self.assertIsNone(r.source_fact_ids)


if __name__ == "__main__":
    unittest.main()
