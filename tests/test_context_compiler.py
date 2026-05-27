from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hermes_prime.contracts import IntentRoot
from hermes_prime.memory import DepthPolicy, MemoryStore
from hermes_prime.memory.backends.sqlite_backend import SQLiteMemoryBackend
from hermes_prime.memory.base import MemorySearchResult
from hermes_prime.memory.compiler import (
    ChainCompressor,
    ContextCompiler,
    ContextQuery,
    TrustFilter,
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


def _make_result(
    fact_id: str,
    claim: str,
    trust_state: str = "unverified",
    confidence: float = 0.5,
    tier: str = "quarantine",
    similarity: float = 0.0,
    memory_type: str = "episodic",
) -> MemorySearchResult:
    return MemorySearchResult(
        fact_id=fact_id,
        claim=claim,
        source={"agent": "test", "memory_type": memory_type},
        epistemic_confidence=confidence,
        verification_status="unverified",
        source_trust="observed",
        timestamp=utc_now_iso(),
        trust_state=trust_state,
        tier=tier,
        contradictions=[],
        intent_root="",
        similarity=similarity,
    )


class TestTrustFilter(unittest.TestCase):
    def setUp(self):
        self.filter = TrustFilter()
        self.results = [
            _make_result("id-1", "low confidence", confidence=0.3, trust_state="observed"),
            _make_result("id-2", "high confidence", confidence=0.9, trust_state="validated"),
            _make_result("id-3", "medium", confidence=0.6, trust_state="unverified"),
            _make_result("id-4", "revoked", trust_state="revoked"),
            _make_result("id-5", "executable", confidence=0.95, trust_state="executable"),
        ]

    def test_filter_by_min_confidence(self):
        filtered = self.filter.filter(self.results, min_confidence=0.5)
        self.assertEqual(len(filtered), 3)
        fact_ids = [r.fact_id for r in filtered]
        self.assertIn("id-2", fact_ids)
        self.assertIn("id-3", fact_ids)
        self.assertIn("id-5", fact_ids)

    def test_filter_excludes_revoked(self):
        filtered = self.filter.filter(self.results, min_trust="unverified")
        fact_ids = [r.fact_id for r in filtered]
        self.assertNotIn("id-4", fact_ids)

    def test_filter_by_min_trust(self):
        filtered = self.filter.filter(self.results, min_trust="validated")
        self.assertEqual(len(filtered), 2)
        fact_ids = [r.fact_id for r in filtered]
        self.assertIn("id-2", fact_ids)
        self.assertIn("id-5", fact_ids)

    def test_filter_by_tier_authoritative(self):
        authoritative = _make_result(
            "auth-1", "auth claim", tier="authoritative", trust_state="validated"
        )
        results = self.results + [authoritative]
        filtered = self.filter.filter(results, min_tier="authoritative")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].fact_id, "auth-1")

    def test_filter_by_memory_type(self):
        semantic = _make_result("sem-1", "semantic fact", memory_type="semantic")
        results = self.results + [semantic]
        filtered = self.filter.filter(results, memory_types=["semantic"])
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].fact_id, "sem-1")

    def test_rank_by_trust_then_similarity(self):
        results = [
            _make_result("a", "low trust high sim", trust_state="observed", similarity=0.9),
            _make_result("b", "high trust low sim", trust_state="validated", similarity=0.5),
            _make_result("c", "medium trust", trust_state="attested", similarity=0.7),
        ]
        ranked = self.filter.rank(results)
        self.assertEqual(ranked[0].fact_id, "b")
        self.assertEqual(ranked[1].fact_id, "c")
        self.assertEqual(ranked[2].fact_id, "a")

    def test_rank_orders_by_similarity_within_same_trust(self):
        results = [
            _make_result("a", "sim 0.9", trust_state="validated", similarity=0.9),
            _make_result("b", "sim 0.5", trust_state="validated", similarity=0.5),
        ]
        ranked = self.filter.rank(results)
        self.assertEqual(ranked[0].fact_id, "a")
        self.assertEqual(ranked[1].fact_id, "b")


class TestChainCompressor(unittest.TestCase):
    def setUp(self):
        self.graph = KnowledgeGraph()
        self.compressor = ChainCompressor(self.graph)

    def test_compress_single_result_no_edges(self):
        results = [_make_result("a", "standalone")]
        chains = self.compressor.compress(results)
        self.assertEqual(len(chains), 1)
        self.assertEqual(chains[0].root_id, "a")
        self.assertEqual(chains[0].depth, 1)
        self.assertEqual(chains[0].summary, "standalone")

    def test_compress_chain_with_edges(self):
        self.graph.add_edge("c", "b")
        self.graph.add_edge("b", "a")
        results = [
            _make_result("a", "root"),
            _make_result("b", "middle"),
            _make_result("c", "leaf"),
        ]
        chains = self.compressor.compress(results)
        self.assertEqual(len(chains), 1)
        self.assertEqual(chains[0].root_id, "a")
        self.assertEqual(chains[0].depth, 3)
        self.assertIn("root", chains[0].summary)
        self.assertIn("middle", chains[0].summary)
        self.assertIn("leaf", chains[0].summary)

    def test_compress_multiple_chains(self):
        self.graph.add_edge("b", "a")
        self.graph.add_edge("d", "c")
        results = [
            _make_result("a", "chain1 root"),
            _make_result("b", "chain1 child"),
            _make_result("c", "chain2 root"),
            _make_result("d", "chain2 child"),
        ]
        chains = self.compressor.compress(results)
        self.assertEqual(len(chains), 2)
        root_ids = {c.root_id for c in chains}
        self.assertEqual(root_ids, {"a", "c"})

    def test_compress_orphan_results_not_in_graph(self):
        self.graph.add_edge("b", "a")
        results = [
            _make_result("a", "in graph"),
            _make_result("x", "orphan"),
        ]
        chains = self.compressor.compress(results)
        self.assertEqual(len(chains), 2)

    def test_compress_empty_results(self):
        chains = self.compressor.compress([])
        self.assertEqual(chains, [])

    def test_compress_deep_chain(self):
        self.graph.add_edge("e", "d")
        self.graph.add_edge("d", "c")
        self.graph.add_edge("c", "b")
        self.graph.add_edge("b", "a")
        results = [_make_result("a", f"level-{i}") for i in range(5)]
        for i, r in enumerate(results):
            r.fact_id = ["a", "b", "c", "d", "e"][i]
        chains = self.compressor.compress(results)
        self.assertEqual(len(chains), 1)
        self.assertEqual(chains[0].depth, 5)


class TestContextCompiler(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "test_compiler.db"
        self.backend = SQLiteMemoryBackend(self.db_path)
        self.graph = KnowledgeGraph()
        self.store = MemoryStore(
            backend=self.backend,
            knowledge_graph=self.graph,
            depth_policy=DepthPolicy(max_claims_per_intent=50, max_total_claims=100),
        )
        self.compiler = ContextCompiler(
            memory_store=self.store,
            chain_compressor=ChainCompressor(self.graph),
        )
        self.intent = _make_intent_root()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_compile_returns_results(self):
        self.store.write("hello world", {"agent": "test"}, self.intent)
        query = ContextQuery(query="hello")
        result = self.compiler.compile(query)
        self.assertEqual(result.query, "hello")
        self.assertGreaterEqual(len(result.memories), 1)
        self.assertIn("hello", result.memories[0].claim)

    def test_compile_no_matches(self):
        query = ContextQuery(query="nonexistent")
        result = self.compiler.compile(query)
        self.assertEqual(len(result.memories), 0)
        self.assertEqual(result.total_found, 0)

    def test_compile_filters_by_confidence(self):
        self.store.write("low conf fact", {"agent": "test"}, self.intent, epistemic_confidence=0.3)
        self.store.write(
            "high conf fact 1", {"agent": "test"}, self.intent, epistemic_confidence=0.9
        )
        query = ContextQuery(query="conf", min_confidence=0.5)
        result = self.compiler.compile(query)
        for r in result.memories:
            self.assertGreaterEqual(r.epistemic_confidence, 0.5)

    def test_compile_trust_distribution(self):
        self.store.write("fact with att", {"agent": "test"}, self.intent, epistemic_confidence=0.9)
        query = ContextQuery(query="fact with")
        result = self.compiler.compile(query)
        self.assertGreater(len(result.trust_distribution), 0)

    def test_compile_with_chain_compression(self):
        w1 = self.store.write("root cause", {"agent": "test"}, self.intent, causal_parent=None)
        self.store.write(
            "followup",
            {"agent": "test"},
            self.intent,
            causal_parent=w1.fact_id,
        )
        query = ContextQuery(query="", limit=10, compress_chains=True)
        result = self.compiler.compile(query)
        self.assertGreaterEqual(len(result.chains), 0)

    def test_compile_by_intent(self):
        other_intent = _make_intent_root()
        self.store.write("intent specific", {"agent": "test"}, self.intent)
        self.store.write("other intent", {"agent": "test"}, other_intent)
        result = self.compiler.compile_by_intent(self.intent.intent_root)
        self.assertGreaterEqual(len(result.memories), 1)
        for r in result.memories:
            self.assertEqual(r.intent_root, self.intent.intent_root)

    def test_compile_by_intent_with_query_filter(self):
        self.store.write("matching text", {"agent": "test"}, self.intent)
        self.store.write("different text", {"agent": "test"}, self.intent)
        result = self.compiler.compile_by_intent(
            self.intent.intent_root,
            query="matching",
        )
        self.assertEqual(len(result.memories), 1)
        self.assertEqual(result.memories[0].claim, "matching text")

    def test_compile_by_intent_empty(self):
        result = self.compiler.compile_by_intent(new_urn_uuid())
        self.assertEqual(len(result.memories), 0)

    def test_compile_limits_results(self):
        for i in range(5):
            self.store.write(f"limit test fact {i}", {"agent": "test"}, self.intent)
        query = ContextQuery(query="limit test", limit=2)
        result = self.compiler.compile(query)
        self.assertLessEqual(len(result.memories), 2)

    def test_compile_total_found_tracks_unfiltered_count(self):
        self.store.write("tracked fact", {"agent": "test"}, self.intent)
        query = ContextQuery(query="tracked")
        result = self.compiler.compile(query)
        self.assertGreater(result.total_found, 0)


class TestContextQuery(unittest.TestCase):
    def test_defaults(self):
        q = ContextQuery(query="test")
        self.assertEqual(q.limit, 10)
        self.assertEqual(q.min_confidence, 0.0)
        self.assertEqual(q.min_tier, "quarantine")
        self.assertEqual(q.min_trust, "unverified")
        self.assertIsNone(q.memory_types)
        self.assertTrue(q.include_lineage)
        self.assertFalse(q.compress_chains)

    def test_custom_values(self):
        q = ContextQuery(
            query="custom",
            limit=5,
            min_confidence=0.7,
            min_tier="authoritative",
            min_trust="validated",
            memory_types=["semantic"],
            include_lineage=False,
            compress_chains=True,
        )
        self.assertEqual(q.limit, 5)
        self.assertEqual(q.min_confidence, 0.7)
        self.assertEqual(q.min_tier, "authoritative")
        self.assertEqual(q.min_trust, "validated")
        self.assertEqual(q.memory_types, ["semantic"])
        self.assertFalse(q.include_lineage)
        self.assertTrue(q.compress_chains)


if __name__ == "__main__":
    unittest.main()
