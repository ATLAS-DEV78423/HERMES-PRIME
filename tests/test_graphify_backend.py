from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hermes_prime.contracts import MemoryClaim, MemoryTier, TrustState
from hermes_prime.memory.backends.graphify_backend import GraphifyBackend
from hermes_prime.utils import new_urn_uuid, utc_now_iso


def _make_claim(text: str = "test claim") -> MemoryClaim:
    return MemoryClaim(
        fact_id=new_urn_uuid(),
        claim=text,
        source={"agent": "test", "memory_type": "episodic"},
        epistemic_confidence=0.5,
        verification_status="unverified",
        source_trust="observed",
        timestamp=utc_now_iso(),
        trust_state=TrustState.UNVERIFIED,
        tier=MemoryTier.QUARANTINE,
        contradictions=[],
        intent_root="",
    )


class TestGraphifyBackend(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "test.db"
        self.backend = GraphifyBackend(
            workspace_path=self.tmp,
            db_path=self.db_path,
        )
        self.backend._graph_built = True

        minimal_graph = {
            "nodes": [
                {"id": "auth_service", "label": "AuthService"},
                {"id": "database", "label": "DatabasePool"},
                {"id": "user_model", "label": "UserModel"},
            ],
            "edges": [
                {"source": "auth_service", "target": "user_model", "relation": "uses"},
                {"source": "user_model", "target": "database", "relation": "persists_to"},
            ],
        }
        self.graph_path = self.tmp / "graphify-out" / "graph.json"
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.graph_path, "w", encoding="utf-8") as f:
            json.dump(minimal_graph, f)
        self.backend.load_existing_graph()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_store_and_get(self):
        claim = _make_claim("stored claim")
        self.backend.store(claim)
        retrieved = self.backend.get(claim.fact_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.fact_id, claim.fact_id)

    def test_get_nonexistent(self):
        self.assertIsNone(self.backend.get("nonexistent"))

    def test_search(self):
        c1 = _make_claim("AuthService handles user login")
        c2 = _make_claim("Database stores user records")
        self.backend.store(c1)
        self.backend.store(c2)
        results = self.backend.search("auth", limit=5)
        self.assertGreaterEqual(len(results), 1)

    def test_search_empty_backend(self):
        results = self.backend.search("test")
        self.assertEqual(results, [])

    def test_list_all(self):
        c1 = _make_claim("first")
        c2 = _make_claim("second")
        self.backend.store(c1)
        self.backend.store(c2)
        claims = self.backend.list_all()
        self.assertEqual(len(claims), 2)

    def test_list_all_empty(self):
        self.assertEqual(self.backend.list_all(), [])

    def test_delete(self):
        claim = _make_claim("deletable")
        self.backend.store(claim)
        self.assertTrue(self.backend.delete(claim.fact_id))
        self.assertIsNone(self.backend.get(claim.fact_id))

    def test_delete_nonexistent(self):
        self.assertFalse(self.backend.delete("nonexistent"))

    def test_count(self):
        self.assertEqual(self.backend.count(), 0)
        self.backend.store(_make_claim("A"))
        self.backend.store(_make_claim("B"))
        self.assertEqual(self.backend.count(), 2)

    def test_gc(self):
        self.backend.store(_make_claim("keep"))
        import datetime as dt

        old_claim = _make_claim("delete me")
        old_claim.timestamp = (
            (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=10))
            .isoformat()
            .replace("+00:00", "Z")
        )
        self.backend.store(old_claim)
        cutoff = (
            (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1))
            .isoformat()
            .replace("+00:00", "Z")
        )
        deleted = self.backend.gc(cutoff)
        self.assertEqual(deleted, 1)

    def test_available_property(self):
        self.assertIsInstance(self.backend.available, bool)

    def test_get_graph_nodes(self):
        nodes = self.backend.get_graph_nodes()
        self.assertEqual(len(nodes), 3)

    def test_get_graph_edges(self):
        edges = self.backend.get_graph_edges()
        self.assertEqual(len(edges), 2)

    def test_query_subgraph(self):
        sub = self.backend.query_subgraph("auth", depth=1)
        self.assertGreaterEqual(len(sub.get("nodes", [])), 1)

    def test_import_edges_to_graph(self):
        from hermes_prime.memory.graph import KnowledgeGraph

        kg = KnowledgeGraph()
        count = self.backend.import_edges_to_graph(kg)
        self.assertEqual(count, 2)

    def test_search_boosted_by_graph(self):
        c1 = _make_claim("the auth service login endpoint handles authentication")
        c2 = _make_claim("Weather forecast for London tomorrow")
        self.backend.store(c1)
        self.backend.store(c2)
        results = self.backend.search("auth service login", limit=5)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].fact_id, c1.fact_id)

    def test_store_updates_existing(self):
        claim = _make_claim("original text")
        self.backend.store(claim)
        claim.claim = "updated text"
        self.backend.store(claim)
        retrieved = self.backend.get(claim.fact_id)
        self.assertEqual(retrieved.claim, "updated text")


if __name__ == "__main__":
    unittest.main()
