from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from hermes_prime.utils import new_urn_uuid, utc_now_iso


class NodeType(str, Enum):
    TOPIC = "topic"
    PROBLEM = "problem"
    SOLUTION = "solution"
    CONCEPT = "concept"
    TASK = "task"
    OUTCOME = "outcome"
    OBSERVATION = "observation"
    PATTERN = "pattern"
    DECISION = "decision"
    REFERENCE = "reference"


class EdgeType(str, Enum):
    SOLVES = "solves"
    CAUSES = "causes"
    RELATES_TO = "relates_to"
    PREREQUISITE = "prerequisite"
    CONTRADICTS = "contradicts"
    EXTENDS = "extends"
    REFERENCES = "references"
    PRODUCES = "produces"
    BLOCKS = "blocks"
    ENABLES = "enables"


@dataclass
class BrainNode:
    node_id: str
    node_type: NodeType
    title: str
    content: str
    tags: list[str]
    confidence: float
    access_count: int
    created_at: str
    updated_at: str
    last_accessed_at: str | None
    source_execution: str | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "title": self.title,
            "content": self.content,
            "tags": list(self.tags),
            "confidence": self.confidence,
            "access_count": self.access_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_accessed_at": self.last_accessed_at,
            "source_execution": self.source_execution,
            "metadata": dict(self.metadata),
        }

    def to_obsidian_note(self) -> str:
        backlinks: list[str] = []
        lines = ["---"]
        lines.append(f"id: {self.node_id}")
        lines.append(f"type: {self.node_type.value}")
        lines.append(f"confidence: {self.confidence}")
        lines.append(f"created: {self.created_at}")
        lines.append(f"updated: {self.updated_at}")
        if self.tags:
            lines.append(f"tags: [{', '.join(self.tags)}]")
        lines.append("---")
        lines.append("")
        lines.append(f"# {self.title}")
        lines.append("")
        lines.append(self.content)
        if backlinks:
            lines.append("")
            lines.append("## Links")
            for bl in backlinks:
                lines.append(f"- [[{bl}]]")
        return "\n".join(lines)

    @property
    def age_days(self) -> float:
        from hermes_prime.utils import parse_iso8601
        import datetime as dt

        created = parse_iso8601(self.created_at)
        return (dt.datetime.now(dt.timezone.utc) - created).total_seconds() / 86400.0


@dataclass
class BrainEdge:
    edge_id: str
    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float
    created_at: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type.value,
            "weight": self.weight,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


class NeuralGraph:
    """Persistent brain graph with typed nodes, labeled edges, and weighted connections."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS brain_nodes (
                node_id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                confidence REAL NOT NULL DEFAULT 0.5,
                access_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_accessed_at TEXT,
                source_execution TEXT,
                metadata TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS brain_edges (
                edge_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                edge_type TEXT NOT NULL,
                weight REAL NOT NULL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (source_id) REFERENCES brain_nodes(node_id),
                FOREIGN KEY (target_id) REFERENCES brain_nodes(node_id),
                UNIQUE(source_id, target_id, edge_type)
            );
            CREATE INDEX IF NOT EXISTS idx_brain_edges_source ON brain_edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_brain_edges_target ON brain_edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_brain_nodes_type ON brain_nodes(node_type);
            CREATE INDEX IF NOT EXISTS idx_brain_nodes_created ON brain_nodes(created_at);
            CREATE INDEX IF NOT EXISTS idx_brain_nodes_tags ON brain_nodes(tags);
        """)
        self._conn.commit()

    def add_node(
        self,
        node_type: NodeType,
        title: str,
        content: str = "",
        tags: list[str] | None = None,
        confidence: float = 0.5,
        source_execution: str | None = None,
        metadata: dict[str, Any] | None = None,
        node_id: str | None = None,
    ) -> BrainNode:
        now = utc_now_iso()
        node = BrainNode(
            node_id=node_id or new_urn_uuid(),
            node_type=node_type,
            title=title,
            content=content,
            tags=tags or [],
            confidence=confidence,
            access_count=0,
            created_at=now,
            updated_at=now,
            last_accessed_at=None,
            source_execution=source_execution,
            metadata=metadata or {},
        )
        import json

        self._conn.execute(
            """INSERT OR REPLACE INTO brain_nodes
               (node_id, node_type, title, content, tags, confidence, access_count,
                created_at, updated_at, last_accessed_at, source_execution, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                node.node_id,
                node.node_type.value,
                node.title,
                node.content,
                json.dumps(node.tags),
                node.confidence,
                node.access_count,
                node.created_at,
                node.updated_at,
                node.last_accessed_at,
                node.source_execution,
                json.dumps(node.metadata),
            ),
        )
        self._conn.commit()
        return node

    def get_node(self, node_id: str) -> BrainNode | None:
        row = self._conn.execute(
            "SELECT * FROM brain_nodes WHERE node_id = ?", (node_id,)
        ).fetchone()
        if row is None:
            return None
        node = self._row_to_node(row)
        self._conn.execute(
            "UPDATE brain_nodes SET access_count = access_count + 1, last_accessed_at = ? WHERE node_id = ?",
            (utc_now_iso(), node_id),
        )
        self._conn.commit()
        return node

    def update_node(self, node_id: str, **kwargs: Any) -> bool:
        allowed = {"title", "content", "tags", "confidence", "metadata", "node_type"}
        updates: list[str] = []
        params: list[Any] = []
        import json

        for key, value in kwargs.items():
            if key in allowed:
                if key == "tags":
                    value = json.dumps(value)
                elif key == "metadata":
                    value = json.dumps(value)
                elif key == "node_type":
                    value = value.value if isinstance(value, NodeType) else value
                updates.append(f"{key} = ?")
                params.append(value)
        if not updates:
            return False
        updates.append("updated_at = ?")
        params.append(utc_now_iso())
        params.append(node_id)
        cursor = self._conn.execute(
            f"UPDATE brain_nodes SET {', '.join(updates)} WHERE node_id = ?",
            params,
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def delete_node(self, node_id: str) -> bool:
        self._conn.execute(
            "DELETE FROM brain_edges WHERE source_id = ? OR target_id = ?", (node_id, node_id)
        )
        cursor = self._conn.execute("DELETE FROM brain_nodes WHERE node_id = ?", (node_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType = EdgeType.RELATES_TO,
        weight: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> BrainEdge | None:
        if source_id == target_id:
            return None
        edge = BrainEdge(
            edge_id=new_urn_uuid(),
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            weight=weight,
            created_at=utc_now_iso(),
            metadata=metadata or {},
        )
        import json

        try:
            self._conn.execute(
                """INSERT OR REPLACE INTO brain_edges
                   (edge_id, source_id, target_id, edge_type, weight, created_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    edge.edge_id,
                    edge.source_id,
                    edge.target_id,
                    edge.edge_type.value,
                    edge.weight,
                    edge.created_at,
                    json.dumps(edge.metadata),
                ),
            )
            self._conn.commit()
            return edge
        except sqlite3.IntegrityError:
            return None

    def get_node_edges(self, node_id: str) -> list[BrainEdge]:
        rows = self._conn.execute(
            "SELECT * FROM brain_edges WHERE source_id = ? OR target_id = ?",
            (node_id, node_id),
        ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def get_neighbors(
        self,
        node_id: str,
        edge_types: list[EdgeType] | None = None,
    ) -> list[tuple[BrainNode, BrainEdge]]:
        edges = self.get_node_edges(node_id)
        results: list[tuple[BrainNode, BrainEdge]] = []
        for edge in edges:
            if edge_types and edge.edge_type not in edge_types:
                continue
            neighbor_id = edge.target_id if edge.source_id == node_id else edge.source_id
            neighbor = self.get_node(neighbor_id)
            if neighbor:
                results.append((neighbor, edge))
        return results

    def find_shortest_path(self, from_id: str, to_id: str) -> list[str] | None:
        visited: set[str] = set()
        queue: list[tuple[str, list[str]]] = [(from_id, [from_id])]
        while queue:
            current, path = queue.pop(0)
            if current == to_id:
                return path
            if current in visited:
                continue
            visited.add(current)
            edges = self._conn.execute(
                "SELECT source_id, target_id FROM brain_edges WHERE source_id = ? OR target_id = ?",
                (current, current),
            ).fetchall()
            for e in edges:
                nxt = e["target_id"] if e["source_id"] == current else e["source_id"]
                if nxt not in visited:
                    queue.append((nxt, path + [nxt]))
        return None

    def search_nodes(
        self,
        query: str,
        node_types: list[NodeType] | None = None,
        limit: int = 20,
    ) -> list[BrainNode]:
        sql = "SELECT * FROM brain_nodes WHERE (title LIKE ? OR content LIKE ?)"
        params: list[Any] = [f"%{query}%", f"%{query}%"]

        tag_sql = " OR tags LIKE ?"
        sql += tag_sql
        params.append(f"%{query.lower()}%")

        if node_types:
            placeholders = ",".join("?" for _ in node_types)
            sql += f" AND node_type IN ({placeholders})"
            params.extend(nt.value for nt in node_types)

        sql += " ORDER BY confidence DESC, access_count DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_node(r) for r in rows]

    def search_by_tags(self, tags: list[str], limit: int = 20) -> list[BrainNode]:
        import json

        results: list[BrainNode] = []
        rows = self._conn.execute(
            "SELECT * FROM brain_nodes ORDER BY confidence DESC, access_count DESC LIMIT ?",
            (limit * 3,),
        ).fetchall()
        for row in rows:
            node_tags = json.loads(row["tags"])
            if any(t in node_tags for t in tags):
                results.append(self._row_to_node(row))
                if len(results) >= limit:
                    break
        return results

    def get_nodes_by_type(self, node_type: NodeType) -> list[BrainNode]:
        rows = self._conn.execute(
            "SELECT * FROM brain_nodes WHERE node_type = ? ORDER BY created_at DESC",
            (node_type.value,),
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def get_all_nodes(self) -> list[BrainNode]:
        rows = self._conn.execute("SELECT * FROM brain_nodes ORDER BY created_at DESC").fetchall()
        return [self._row_to_node(r) for r in rows]

    def get_all_edges(self) -> list[BrainEdge]:
        rows = self._conn.execute("SELECT * FROM brain_edges").fetchall()
        return [self._row_to_edge(r) for r in rows]

    def count_nodes(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM brain_nodes").fetchone()[0]

    def count_edges(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM brain_edges").fetchone()[0]

    def get_metrics(self) -> dict[str, Any]:
        by_type: Counter = Counter()
        for row in self._conn.execute(
            "SELECT node_type, COUNT(*) as cnt FROM brain_nodes GROUP BY node_type"
        ):
            by_type[row["node_type"]] = row["cnt"]
        by_edge: Counter = Counter()
        for row in self._conn.execute(
            "SELECT edge_type, COUNT(*) as cnt FROM brain_edges GROUP BY edge_type"
        ):
            by_edge[row["edge_type"]] = row["cnt"]
        total_nodes = self.count_nodes()
        return {
            "total_nodes": total_nodes,
            "total_edges": self.count_edges(),
            "by_node_type": dict(by_type),
            "by_edge_type": dict(by_edge),
            "avg_confidence": round(
                self._conn.execute("SELECT AVG(confidence) FROM brain_nodes").fetchone()[0] or 0.0,
                3,
            )
            if total_nodes
            else 0.0,
        }

    def clear(self) -> None:
        self._conn.execute("DELETE FROM brain_edges")
        self._conn.execute("DELETE FROM brain_nodes")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _row_to_node(self, row: sqlite3.Row) -> BrainNode:
        import json

        return BrainNode(
            node_id=row["node_id"],
            node_type=NodeType(row["node_type"]),
            title=row["title"],
            content=row["content"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            confidence=row["confidence"],
            access_count=row["access_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_accessed_at=row["last_accessed_at"],
            source_execution=row["source_execution"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def _row_to_edge(self, row: sqlite3.Row) -> BrainEdge:
        import json

        return BrainEdge(
            edge_id=row["edge_id"],
            source_id=row["source_id"],
            target_id=row["target_id"],
            edge_type=EdgeType(row["edge_type"]),
            weight=row["weight"],
            created_at=row["created_at"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
