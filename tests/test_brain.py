"""Tests for the neural brain network system."""
from __future__ import annotations

import os
import tempfile

from pathlib import Path

from hermes_prime.brain import (
    NeuralGraph, BrainJournal, AutoLinker, BrainMaintenanceAgent,
    NodeType, EdgeType, BrainNode, BrainEdge,
)
from hermes_prime.utils import new_urn_uuid, utc_now_iso


def test_neural_graph_node_crud():
    with tempfile.TemporaryDirectory() as tmp:
        g = NeuralGraph(os.path.join(tmp, "brain.db"))

        node = g.add_node(NodeType.OBSERVATION, "Test Node", "This is test content",
                          tags=["test", "observation"])
        assert node.node_id is not None
        assert node.title == "Test Node"
        assert node.node_type == NodeType.OBSERVATION
        assert node.confidence == 0.5

        fetched = g.get_node(node.node_id)
        assert fetched is not None
        assert fetched.title == "Test Node"

        updated = g.update_node(node.node_id, title="Updated Node", confidence=0.9)
        assert updated is True

        updated_node = g.get_node(node.node_id)
        assert updated_node is not None
        assert updated_node.title == "Updated Node"
        assert updated_node.confidence == 0.9

        deleted = g.delete_node(node.node_id)
        assert deleted is True
        assert g.get_node(node.node_id) is None
        g.close()
    print("NeuralGraph CRUD: OK")


def test_neural_graph_edges():
    with tempfile.TemporaryDirectory() as tmp:
        g = NeuralGraph(os.path.join(tmp, "brain.db"))

        a = g.add_node(NodeType.PROBLEM, "Bug in parser", "Parser crashes on null input")
        b = g.add_node(NodeType.SOLUTION, "Add null check", "Added null guard clause")

        edge = g.add_edge(a.node_id, b.node_id, EdgeType.SOLVES, weight=1.0)
        assert edge is not None
        assert edge.edge_type == EdgeType.SOLVES

        edges = g.get_node_edges(a.node_id)
        assert len(edges) == 1
        assert edges[0].target_id == b.node_id or edges[0].source_id == b.node_id

        neighbors = g.get_neighbors(a.node_id)
        assert len(neighbors) == 1
        assert neighbors[0][0].node_id == b.node_id

        path = g.find_shortest_path(a.node_id, b.node_id)
        assert path is not None
        assert len(path) == 2

        g.close()
    print("NeuralGraph edges: OK")


def test_brain_journal():
    with tempfile.TemporaryDirectory() as tmp:
        g = NeuralGraph(os.path.join(tmp, "brain.db"))
        journal = BrainJournal(g)

        problem = journal.write_problem("Database connection fails",
                                        "Cannot connect to SQLite on high load",
                                        context="production deployment")
        assert problem.node_type == NodeType.PROBLEM
        assert problem.metadata.get("solved") is False

        solution = journal.write_solution(
            "Add connection pooling",
            "Implemented SQLite WAL mode with connection pool",
            problem.node_id,
            outcome="success",
        )
        assert solution is not None
        assert solution.node_type == NodeType.SOLUTION

        problem_updated = g.get_node(problem.node_id)
        assert problem_updated is not None
        assert problem_updated.metadata.get("solved") is True
        assert problem_updated.metadata.get("solution_count", 0) >= 1

        solutions = journal.get_solutions_for_problem(problem.node_id)
        assert len(solutions) == 1
        assert solutions[0].node_id == solution.node_id

        path = journal.get_solution_path(problem.node_id)
        assert len(path) >= 2
        assert path[0]["type"] == "problem"
        assert path[1]["type"] == "solution"

        unsolved = journal.get_problems_unsolved()
        assert len(unsolved) == 0

        obs = journal.write_observation("System running smoothly",
                                        "Everything works after pooling fix",
                                        tags=["observations"])
        assert obs.node_type == NodeType.OBSERVATION

        pattern = journal.write_pattern("Pooling pattern",
                                        "Always use connection pooling for SQLite",
                                        confidence=0.9)
        assert pattern.node_type == NodeType.PATTERN

        decision = journal.write_decision("Use WAL mode",
                                          "WAL mode provides better concurrency")
        assert decision.node_type == NodeType.DECISION

        g.close()
    print("BrainJournal: OK")


def test_auto_linker():
    with tempfile.TemporaryDirectory() as tmp:
        g = NeuralGraph(os.path.join(tmp, "brain.db"))
        linker = AutoLinker(g)

        a = g.add_node(NodeType.TOPIC, "Python error handling",
                       "How to handle exceptions in Python",
                       tags=["python", "errors"])
        b = g.add_node(NodeType.TOPIC, "Exception best practices",
                        "Best practices for Python exception handling",
                        tags=["python", "best-practices"])

        links = linker.link_new_node(a.node_id)
        assert links > 0

        neighbors = g.get_neighbors(b.node_id)
        neighbor_ids = {n.node_id for n, _ in neighbors}
        assert a.node_id in neighbor_ids

        related = linker.find_related(a.node_id, min_weight=0.1)
        assert len(related) > 0

        suggested = linker.suggest_tags("Python exception handling patterns")
        assert len(suggested) > 0

        tags = linker.suggest_tags("completely unrelated topic about cooking pasta")
        g.close()
    print("AutoLinker: OK")


def test_maintenance_agent():
    with tempfile.TemporaryDirectory() as tmp:
        g = NeuralGraph(os.path.join(tmp, "brain.db"))
        linker = AutoLinker(g)
        agent = BrainMaintenanceAgent(g, linker)

        import datetime as dt
        old_ts = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=200)).isoformat().replace("+00:00", "Z")

        stale1 = g.add_node(NodeType.OBSERVATION, "Old stale node",
                            "This is very old and never accessed",
                            confidence=0.1, tags=[])
        stale2 = g.add_node(NodeType.OBSERVATION, "Another stale",
                            "Also old and unimportant",
                            confidence=0.15, tags=[])

        g._conn.execute(
            "UPDATE brain_nodes SET created_at = ?, access_count = 0 WHERE node_id IN (?, ?)",
            (old_ts, stale1.node_id, stale2.node_id),
        )

        old_node = g.add_node(NodeType.TOPIC, "Important old topic",
                              "Still relevant", confidence=0.8, tags=["important"])
        g._conn.execute(
            "UPDATE brain_nodes SET created_at = ?, access_count = 0 WHERE node_id = ?",
            (old_ts, old_node.node_id),
        )
        g._conn.commit()

        stale_nodes = [n for n in g.get_all_nodes() if n.confidence < 0.2]
        assert len(stale_nodes) >= 2

        report = agent.run_maintenance(dry_run=True, max_age_days=30, min_confidence=0.2)
        assert report["dry_run"] is True
        assert report["pruned_nodes"] > 0

        report2 = agent.run_maintenance(dry_run=False, max_age_days=30, min_confidence=0.2)
        assert report2["remaining_nodes"] > 0

        health = agent.get_health_report()
        assert health["total_nodes"] > 0
        assert 0 <= health["health_score"] <= 1.0
        assert health["orphaned_nodes"] >= 0

        g.close()
    print("BrainMaintenance: OK")


def test_obsidian_export():
    with tempfile.TemporaryDirectory() as tmp:
        g = NeuralGraph(os.path.join(tmp, "brain.db"))
        journal = BrainJournal(g)
        linker = AutoLinker(g)

        a = g.add_node(NodeType.TOPIC, "Machine Learning",
                       "Machine learning concepts and techniques",
                       tags=["ml", "ai"])
        b = g.add_node(NodeType.TOPIC, "Neural Networks",
                       "Neural network architectures",
                       tags=["ml", "deep-learning"])
        linker.link_new_node(a.node_id)
        linker.link_new_node(b.node_id)

        export_dir = os.path.join(tmp, "obsidian-vault")
        result = journal.export_obsidian_vault(export_dir)
        assert result["notes_exported"] >= 2
        assert result["links_exported"] >= 0
        assert os.path.exists(os.path.join(export_dir, "index.md"))

        files = os.listdir(export_dir)
        md_files = [f for f in files if f.endswith(".md")]
        assert len(md_files) >= 3

        index_content = open(os.path.join(export_dir, "index.md")).read()
        assert "Machine Learning" in index_content
        assert "Neural Networks" in index_content

        g.close()
    print("Obsidian export: OK")


def test_metrics():
    with tempfile.TemporaryDirectory() as tmp:
        g = NeuralGraph(os.path.join(tmp, "brain.db"))

        g.add_node(NodeType.TOPIC, "T1", "", tags=["a"])
        g.add_node(NodeType.PROBLEM, "P1", "", tags=["b"])
        g.add_node(NodeType.SOLUTION, "S1", "", tags=["c"])
        g.add_node(NodeType.OBSERVATION, "O1", "", tags=["d"])

        a = g.get_all_nodes()[0]
        b = g.get_all_nodes()[1]
        g.add_edge(a.node_id, b.node_id, EdgeType.RELATES_TO)

        metrics = g.get_metrics()
        assert metrics["total_nodes"] == 4
        assert metrics["total_edges"] == 1
        assert metrics["by_node_type"]["topic"] == 1
        assert metrics["by_node_type"]["problem"] == 1
        assert metrics["by_node_type"]["solution"] == 1

        count = g.count_nodes()
        assert count == 4

        g.close()
    print("Brain metrics: OK")


if __name__ == "__main__":
    test_neural_graph_node_crud()
    test_neural_graph_edges()
    test_brain_journal()
    test_auto_linker()
    test_maintenance_agent()
    test_obsidian_export()
    test_metrics()
    print("\nAll brain tests passed!")
