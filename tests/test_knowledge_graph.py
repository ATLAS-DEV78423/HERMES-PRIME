from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from hermes_prime.memory.graph import KnowledgeGraph


class TestKnowledgeGraph(unittest.TestCase):
    def setUp(self):
        self.graph = KnowledgeGraph()

    def test_add_edge_and_get_lineage(self):
        self.graph.add_edge("child", "parent")
        self.assertEqual(self.graph.get_lineage("child"), ["parent"])

    def test_get_lineage_multi_level(self):
        self.graph.add_edge("c", "b")
        self.graph.add_edge("b", "a")
        self.assertEqual(self.graph.get_lineage("c"), ["b", "a"])

    def test_get_lineage_no_ancestors(self):
        self.assertEqual(self.graph.get_lineage("orphan"), [])

    def test_get_descendants(self):
        self.graph.add_edge("b", "a")
        self.graph.add_edge("c", "a")
        self.graph.add_edge("d", "b")
        descendants = self.graph.get_descendants("a")
        self.assertIn("b", descendants)
        self.assertIn("c", descendants)
        self.assertIn("d", descendants)

    def test_get_descendants_leaf(self):
        self.graph.add_edge("b", "a")
        self.assertEqual(self.graph.get_descendants("b"), [])

    def test_get_path_direct(self):
        self.graph.add_edge("b", "a")
        self.graph.add_edge("c", "b")
        path = self.graph.get_path("a", "c")
        self.assertEqual(path, ["a", "b", "c"])

    def test_get_path_no_path(self):
        self.graph.add_edge("b", "a")
        self.graph.add_edge("d", "c")
        path = self.graph.get_path("a", "d")
        self.assertIsNone(path)

    def test_get_path_same_node(self):
        path = self.graph.get_path("x", "x")
        self.assertEqual(path, ["x"])

    def test_remove_node(self):
        self.graph.add_edge("b", "a")
        self.graph.add_edge("c", "b")
        self.graph.remove_node("b")
        self.assertFalse(self.graph.has_node("b"))
        self.assertFalse(self.graph.has_node("c"))
        self.assertTrue(self.graph.has_node("a"))

    def test_remove_node_orphan(self):
        self.graph.add_edge("b", "a")
        self.graph.remove_node("x")
        self.assertEqual(self.graph.edge_count(), 1)

    def test_has_node(self):
        self.assertFalse(self.graph.has_node("x"))
        self.graph.add_edge("b", "a")
        self.assertTrue(self.graph.has_node("a"))
        self.assertTrue(self.graph.has_node("b"))

    def test_edge_count(self):
        self.assertEqual(self.graph.edge_count(), 0)
        self.graph.add_edge("b", "a")
        self.assertEqual(self.graph.edge_count(), 1)
        self.graph.add_edge("c", "b")
        self.assertEqual(self.graph.edge_count(), 2)

    def test_self_referential_edge_raises(self):
        with self.assertRaises(ValueError):
            self.graph.add_edge("a", "a")

    def test_clear(self):
        self.graph.add_edge("b", "a")
        self.graph.add_edge("c", "b")
        self.graph.clear()
        self.assertEqual(self.graph.edge_count(), 0)
        self.assertFalse(self.graph.has_node("a"))
        self.assertEqual(self.graph.get_lineage("b"), [])

    def test_get_descendants_breadth_first_order(self):
        self.graph.add_edge("b", "a")
        self.graph.add_edge("c", "a")
        self.graph.add_edge("d", "b")
        desc = self.graph.get_descendants("a")
        self.assertEqual(desc[0:2], ["b", "c"])

    def test_get_ancestors_alias(self):
        self.graph.add_edge("c", "b")
        self.graph.add_edge("b", "a")
        self.assertEqual(self.graph.get_ancestors("c"), ["b", "a"])


class TestKnowledgeGraphPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "graph.db"

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_persistence(self):
        g1 = KnowledgeGraph(self.db_path)
        g1.add_edge("c", "b")
        g1.add_edge("b", "a")
        del g1

        g2 = KnowledgeGraph(self.db_path)
        self.assertEqual(g2.get_lineage("c"), ["b", "a"])
        self.assertEqual(g2.get_descendants("a"), ["b", "c"])
        self.assertEqual(g2.edge_count(), 2)

    def test_persistence_clear(self):
        g1 = KnowledgeGraph(self.db_path)
        g1.add_edge("b", "a")
        g1.clear()
        del g1

        g2 = KnowledgeGraph(self.db_path)
        self.assertEqual(g2.edge_count(), 0)

    def test_persistence_remove(self):
        g1 = KnowledgeGraph(self.db_path)
        g1.add_edge("b", "a")
        g1.add_edge("c", "b")
        g1.remove_node("b")
        del g1

        g2 = KnowledgeGraph(self.db_path)
        self.assertEqual(g2.edge_count(), 0)

    def test_in_memory_no_db_file_created(self):
        g = KnowledgeGraph()
        g.add_edge("b", "a")
        self.assertFalse(os.path.exists(str(self.db_path)))

    def test_multiple_edges_same_parent(self):
        g = KnowledgeGraph(self.db_path)
        g.add_edge("b", "a")
        g.add_edge("c", "a")
        g.add_edge("d", "a")
        del g

        g2 = KnowledgeGraph(self.db_path)
        self.assertEqual(len(g2.get_descendants("a")), 3)


if __name__ == "__main__":
    unittest.main()
