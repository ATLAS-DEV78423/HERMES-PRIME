from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hermes_prime.memory.graphify_bridge import GraphifyBridge


class TestGraphifyBridge(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.bridge = GraphifyBridge(workspace_path=self.tmp)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_available_checks_graphify_installed(self):
        result = self.bridge.available
        self.assertIsInstance(result, bool)

    def test_no_graph_initially(self):
        self.assertIsNone(self.bridge.load_graph())

    def test_load_nonexistent_graph_path(self):
        result = self.bridge.load_graph(graph_path=self.tmp / "nonexistent.json")
        self.assertIsNone(result)

    def test_get_nodes_empty_when_no_graph(self):
        self.assertEqual(self.bridge.get_nodes(), [])

    def test_get_edges_empty_when_no_graph(self):
        self.assertEqual(self.bridge.get_edges(), [])

    def test_search_nodes_empty_when_no_graph(self):
        self.assertEqual(self.bridge.search_nodes("test"), [])

    def test_load_minimal_graph(self):
        minimal = {
            "nodes": [
                {"id": "node1", "label": "TestNode"},
                {"id": "node2", "label": "AnotherNode"},
            ],
            "edges": [
                {"source": "node1", "target": "node2", "relation": "depends_on"},
            ],
        }
        graph_path = self.tmp / "graph.json"
        with open(graph_path, "w", encoding="utf-8") as f:
            json.dump(minimal, f)
        result = self.bridge.load_graph(graph_path=graph_path)
        self.assertIsNotNone(result)
        self.assertEqual(len(self.bridge.get_nodes()), 2)
        self.assertEqual(len(self.bridge.get_edges()), 1)

    def test_get_neighbors(self):
        graph = {
            "nodes": [
                {"id": "a", "label": "A"},
                {"id": "b", "label": "B"},
                {"id": "c", "label": "C"},
            ],
            "edges": [
                {"source": "a", "target": "b", "relation": "calls"},
                {"source": "a", "target": "c", "relation": "imports"},
            ],
        }
        graph_path = self.tmp / "graph.json"
        with open(graph_path, "w", encoding="utf-8") as f:
            json.dump(graph, f)
        self.bridge.load_graph(graph_path=graph_path)
        neighbors = self.bridge.get_neighbors("a")
        self.assertEqual(len(neighbors), 2)
        neighbor_ids = {n["node_id"] for n in neighbors}
        self.assertIn("b", neighbor_ids)
        self.assertIn("c", neighbor_ids)

    def test_get_neighbors_no_edges(self):
        self.assertEqual(self.bridge.get_neighbors("nonexistent"), [])

    def test_search_nodes_finds_matching(self):
        graph = {
            "nodes": [
                {"id": "auth", "label": "AuthService"},
                {"id": "db", "label": "DatabasePool"},
                {"id": "cache", "label": "RedisCache"},
            ],
            "edges": [],
        }
        graph_path = self.tmp / "graph.json"
        with open(graph_path, "w", encoding="utf-8") as f:
            json.dump(graph, f)
        self.bridge.load_graph(graph_path=graph_path)
        results = self.bridge.search_nodes("auth")
        self.assertGreaterEqual(len(results), 1)
        labels = [n.get("label") for n in results]
        self.assertIn("AuthService", labels)

    def test_search_nodes_ranked_by_relevance(self):
        graph = {
            "nodes": [
                {"id": "a", "label": "UserAuthService"},
                {"id": "b", "label": "RequestHandler"},
                {"id": "c", "label": "AuthProvider"},
            ],
            "edges": [],
        }
        graph_path = self.tmp / "graph.json"
        with open(graph_path, "w", encoding="utf-8") as f:
            json.dump(graph, f)
        self.bridge.load_graph(graph_path=graph_path)
        results = self.bridge.search_nodes("user auth")
        self.assertGreaterEqual(len(results), 2)
        labels = [n.get("label") for n in results]
        self.assertEqual(labels[0], "UserAuthService")
        self.assertEqual(labels[-1], "AuthProvider")

    def test_query_subgraph(self):
        graph = {
            "nodes": [
                {"id": "a", "label": "AuthService"},
                {"id": "b", "label": "UserService"},
                {"id": "c", "label": "Database"},
                {"id": "d", "label": "Logger"},
            ],
            "edges": [
                {"source": "a", "target": "b", "relation": "calls"},
                {"source": "b", "target": "c", "relation": "queries"},
                {"source": "a", "target": "d", "relation": "uses"},
            ],
        }
        graph_path = self.tmp / "graph.json"
        with open(graph_path, "w", encoding="utf-8") as f:
            json.dump(graph, f)
        self.bridge.load_graph(graph_path=graph_path)
        sub = self.bridge.query_subgraph("auth", depth=1)
        self.assertGreaterEqual(len(sub["nodes"]), 2)
        self.assertGreaterEqual(len(sub["edges"]), 1)

    def test_query_subgraph_no_match(self):
        graph = {"nodes": [{"id": "a", "label": "Alpha"}], "edges": []}
        graph_path = self.tmp / "graph.json"
        with open(graph_path, "w", encoding="utf-8") as f:
            json.dump(graph, f)
        self.bridge.load_graph(graph_path=graph_path)
        sub = self.bridge.query_subgraph("zxy_nonexistent")
        self.assertEqual(sub["nodes"], [])
        self.assertEqual(sub["edges"], [])

    def test_import_to_knowledge_graph(self):
        from hermes_prime.memory.graph import KnowledgeGraph

        graph = {
            "nodes": [
                {"id": "a", "label": "ServiceA"},
                {"id": "b", "label": "ServiceB"},
                {"id": "c", "label": "ServiceC"},
            ],
            "edges": [
                {"source": "a", "target": "b", "relation": "depends"},
                {"source": "b", "target": "c", "relation": "depends"},
            ],
        }
        graph_path = self.tmp / "graph.json"
        with open(graph_path, "w", encoding="utf-8") as f:
            json.dump(graph, f)
        self.bridge.load_graph(graph_path=graph_path)

        kg = KnowledgeGraph()
        count = self.bridge.import_to_knowledge_graph(kg)
        self.assertEqual(count, 2)
        self.assertTrue(kg.has_node("a"))
        self.assertTrue(kg.has_node("b"))
        self.assertTrue(kg.has_node("c"))

    def test_import_skips_self_loops(self):
        from hermes_prime.memory.graph import KnowledgeGraph

        graph = {
            "nodes": [{"id": "a", "label": "A"}],
            "edges": [{"source": "a", "target": "a", "relation": "self_ref"}],
        }
        graph_path = self.tmp / "graph.json"
        with open(graph_path, "w", encoding="utf-8") as f:
            json.dump(graph, f)
        self.bridge.load_graph(graph_path=graph_path)
        kg = KnowledgeGraph()
        count = self.bridge.import_to_knowledge_graph(kg)
        self.assertEqual(count, 0)

    def test_links_fallback(self):
        graph = {
            "nodes": [{"id": "x", "label": "X"}, {"id": "y", "label": "Y"}],
            "links": [{"source": "x", "target": "y", "relation": "connects"}],
        }
        graph_path = self.tmp / "graph.json"
        with open(graph_path, "w", encoding="utf-8") as f:
            json.dump(graph, f)
        self.bridge.load_graph(graph_path=graph_path)
        edges = self.bridge.get_edges()
        self.assertEqual(len(edges), 1)


if __name__ == "__main__":
    unittest.main()
