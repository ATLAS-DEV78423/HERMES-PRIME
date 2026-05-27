from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hermes_prime.brain.neural_graph import NeuralGraph, BrainNode, NodeType, EdgeType


class BrainJournal:
    """Persistent brain journal with Obsidian-compatible markdown export.

    The journal stores everything the agent learns as an interconnected neural
    network of typed nodes. It can export to Obsidian vault format with
    [[wikilinks]] for human review.
    """

    def __init__(self, graph: NeuralGraph):
        self.graph = graph

    def write_observation(
        self,
        title: str,
        content: str,
        tags: list[str] | None = None,
        confidence: float = 0.7,
        source_execution: str | None = None,
        link_to: list[str] | None = None,
    ) -> BrainNode:
        """Write an observation to the brain, auto-linking to related nodes."""
        node = self.graph.add_node(
            node_type=NodeType.OBSERVATION,
            title=title,
            content=content,
            tags=tags or [],
            confidence=confidence,
            source_execution=source_execution,
        )
        if link_to:
            for target_id in link_to:
                self.graph.add_edge(
                    source_id=node.node_id,
                    target_id=target_id,
                    edge_type=EdgeType.RELATES_TO,
                    weight=confidence,
                )
        return node

    def write_problem(
        self,
        title: str,
        description: str,
        tags: list[str] | None = None,
        context: str | None = None,
        source_execution: str | None = None,
    ) -> BrainNode:
        """Record a problem encountered during execution."""
        metadata: dict[str, Any] = {"solved": False, "solution_count": 0}
        if context:
            metadata["context"] = context
        return self.graph.add_node(
            node_type=NodeType.PROBLEM,
            title=title,
            content=description,
            tags=(tags or []) + ["problem"],
            confidence=1.0,
            source_execution=source_execution,
            metadata=metadata,
        )

    def write_solution(
        self,
        title: str,
        description: str,
        problem_id: str,
        outcome: str = "unknown",
        tags: list[str] | None = None,
        source_execution: str | None = None,
    ) -> BrainNode | None:
        """Record a solution and link it to the problem it solves."""
        problem = self.graph.get_node(problem_id)
        if problem is None:
            return None

        solution = self.graph.add_node(
            node_type=NodeType.SOLUTION,
            title=title,
            content=description,
            tags=(tags or []) + ["solution"],
            confidence=0.8,
            source_execution=source_execution,
            metadata={"solves_problem": problem_id, "outcome": outcome},
        )
        self.graph.add_edge(
            source_id=solution.node_id,
            target_id=problem_id,
            edge_type=EdgeType.SOLVES,
            weight=1.0,
            metadata={"outcome": outcome},
        )

        problem.metadata["solved"] = outcome == "success"
        problem.metadata["solution_count"] = problem.metadata.get("solution_count", 0) + 1
        self.graph.update_node(problem_id, metadata=problem.metadata)
        return solution

    def write_topic(
        self,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> BrainNode:
        return self.graph.add_node(
            node_type=NodeType.TOPIC,
            title=title,
            content=content,
            tags=tags or [],
            confidence=0.6,
        )

    def write_pattern(
        self,
        title: str,
        content: str,
        confidence: float = 0.7,
        tags: list[str] | None = None,
        source_execution: str | None = None,
    ) -> BrainNode:
        return self.graph.add_node(
            node_type=NodeType.PATTERN,
            title=title,
            content=content,
            tags=(tags or []) + ["pattern"],
            confidence=confidence,
            source_execution=source_execution,
        )

    def write_decision(
        self,
        title: str,
        rationale: str,
        tags: list[str] | None = None,
        source_execution: str | None = None,
    ) -> BrainNode:
        return self.graph.add_node(
            node_type=NodeType.DECISION,
            title=title,
            content=rationale,
            tags=(tags or []) + ["decision"],
            confidence=0.9,
            source_execution=source_execution,
        )

    def link_nodes(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType = EdgeType.RELATES_TO,
        weight: float = 1.0,
    ) -> None:
        self.graph.add_edge(source_id, target_id, edge_type, weight)

    def get_problems_unsolved(self) -> list[BrainNode]:
        all_problems = self.graph.get_nodes_by_type(NodeType.PROBLEM)
        return [p for p in all_problems if not p.metadata.get("solved", False)]

    def get_solutions_for_problem(self, problem_id: str) -> list[BrainNode]:
        edges = self.graph.get_node_edges(problem_id)
        solution_ids: list[str] = []
        for e in edges:
            if e.edge_type == EdgeType.SOLVES:
                sid = e.source_id if e.target_id == problem_id else e.target_id
                solution_ids.append(sid)
        return [n for n in (self.graph.get_node(sid) for sid in solution_ids) if n is not None]

    def get_solution_path(self, problem_id: str) -> list[dict[str, Any]]:
        """Trace the full path: problem -> solutions -> outcomes -> related topics."""
        path: list[dict[str, Any]] = []
        problem = self.graph.get_node(problem_id)
        if not problem:
            return path
        path.append({"type": "problem", "node": problem.to_dict()})
        solutions = self.get_solutions_for_problem(problem_id)
        for sol in solutions:
            path.append({"type": "solution", "node": sol.to_dict()})
            neighbors = self.graph.get_neighbors(sol.node_id)
            for neighbor, edge in neighbors:
                if neighbor.node_id != problem_id:
                    path.append(
                        {
                            "type": f"related_{neighbor.node_type.value}",
                            "node": neighbor.to_dict(),
                            "via": edge.edge_type.value,
                        }
                    )
        return path

    def export_obsidian_vault(self, output_dir: str | Path) -> dict[str, Any]:
        """Export the entire brain as an Obsidian-compatible markdown vault."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        nodes = self.graph.get_all_nodes()
        edge_map: dict[str, list[tuple[str, str, str]]] = {}
        for edge in self.graph.get_all_edges():
            edge_map.setdefault(edge.source_id, []).append(
                (edge.target_id, edge.edge_type.value, str(edge.weight))
            )
            edge_map.setdefault(edge.target_id, []).append(
                (edge.source_id, edge.edge_type.value, str(edge.weight))
            )

        counts: dict[str, int] = {"notes": 0, "links": 0}
        for node in nodes:
            safe_name = node.title.replace("/", "-").replace(":", "-").replace(" ", "_")[:80]
            filename = f"{safe_name}_{node.node_id[-8:]}.md"
            filepath = out / filename

            links = edge_map.get(node.node_id, [])
            counts["links"] += len(links)

            wiki_lines = []
            for target_id, etype, weight in links:
                target = self.graph.get_node(target_id)
                if target:
                    target_safe = (
                        target.title.replace("/", "-").replace(":", "-").replace(" ", "_")[:80]
                    )
                    target_file = f"{target_safe}_{target.node_id[-8:]}"
                    wiki_lines.append(f"- [[{target_file}|{target.title}]] _{etype}_ (w:{weight})")

            frontmatter = {
                "id": node.node_id,
                "type": node.node_type.value,
                "confidence": node.confidence,
                "tags": node.tags,
                "created": node.created_at,
                "updated": node.updated_at,
                "access_count": node.access_count,
                "links": len(links),
            }
            parts = [
                "---",
                json.dumps(frontmatter, indent=2),
                "---",
                "",
                f"# {node.title}",
                "",
                node.content,
            ]
            if wiki_lines:
                parts.extend(["", "## Connections", ""] + wiki_lines)
            parts.append("")

            filepath.write_text("\n".join(parts), encoding="utf-8")
            counts["notes"] += 1

        index_lines = [
            "# Hermes-Prime Brain",
            "",
            f"Total notes: {counts['notes']}",
            f"Total connections: {counts['links']}",
            "",
            "## By Type",
            "",
        ]
        by_type: dict[str, int] = {}
        for n in nodes:
            by_type[n.node_type.value] = by_type.get(n.node_type.value, 0) + 1
        for t, c in sorted(by_type.items()):
            index_lines.append(f"- **{t}**: {c}")

        index_lines.extend(["", "## Recent Notes", ""])
        recent = sorted(nodes, key=lambda n: n.created_at, reverse=True)[:20]
        for n in recent:
            safe = n.title.replace("/", "-").replace(":", "-").replace(" ", "_")[:80]
            fname = f"{safe}_{n.node_id[-8:]}"
            index_lines.append(f"- [[{fname}|{n.title}]] _(confidence: {n.confidence})_")

        (out / "index.md").write_text("\n".join(index_lines), encoding="utf-8")

        return {
            "notes_exported": counts["notes"],
            "links_exported": counts["links"],
            "vault_path": str(out.resolve()),
        }
