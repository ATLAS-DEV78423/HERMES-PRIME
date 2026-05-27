from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..contracts import AgentNode, AgentStatus, AgentSpawnAttestation
from ..utils import new_urn_uuid


class AgentMeshError(Exception):
    pass


class AgentNotFoundError(AgentMeshError):
    pass


class DepthLimitError(AgentMeshError):
    pass


class AgentMesh:
    def __init__(self, max_depth: int = 5, db_path: str | None = None) -> None:
        self._nodes: dict[str, AgentNode] = {}
        self._children_of: dict[str, set[str]] = {}
        self._max_depth = max_depth
        self._conn: sqlite3.Connection | None = None
        if db_path is not None:
            resolved = Path(db_path).resolve()
            resolved.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(resolved))
            self._conn.row_factory = sqlite3.Row
            self._init_schema()
            self._load_from_db()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS agent_mesh (
                agent_id TEXT PRIMARY KEY,
                parent_id TEXT,
                intent_root TEXT NOT NULL,
                capability_scope TEXT NOT NULL,
                capability_token TEXT,
                spawned_by TEXT,
                spawned_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                depth INTEGER NOT NULL,
                task_description TEXT NOT NULL,
                result TEXT,
                attestation TEXT
            );
        """)
        self._conn.commit()

    def _load_from_db(self) -> None:
        rows = self._conn.execute("SELECT * FROM agent_mesh").fetchall()
        for row in rows:
            node = self._row_to_node(row)
            self._nodes[node.agent_id] = node
            if node.parent_id:
                self._children_of.setdefault(node.parent_id, set()).add(node.agent_id)

    @staticmethod
    def _row_to_node(row: sqlite3.Row) -> AgentNode:
        result = json.loads(row["result"]) if row["result"] else None
        attestation = json.loads(row["attestation"]) if row["attestation"] else None
        return AgentNode(
            agent_id=row["agent_id"],
            parent_id=row["parent_id"],
            intent_root=row["intent_root"],
            capability_scope=row["capability_scope"],
            capability_token=row["capability_token"],
            spawned_by=row["spawned_by"],
            spawned_at=row["spawned_at"],
            completed_at=row["completed_at"],
            status=AgentStatus(row["status"]),
            depth=row["depth"],
            task_description=row["task_description"],
            result=result,
            attestation=AgentSpawnAttestation(**attestation) if attestation else None,
        )

    def _persist_upsert(self, node: AgentNode) -> None:
        if self._conn is None:
            return
        self._conn.execute(
            """
            INSERT INTO agent_mesh(agent_id, parent_id, intent_root, capability_scope, capability_token, spawned_by, spawned_at, completed_at, status, depth, task_description, result, attestation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET
                parent_id=excluded.parent_id,
                intent_root=excluded.intent_root,
                capability_scope=excluded.capability_scope,
                capability_token=excluded.capability_token,
                spawned_by=excluded.spawned_by,
                spawned_at=excluded.spawned_at,
                completed_at=excluded.completed_at,
                status=excluded.status,
                depth=excluded.depth,
                task_description=excluded.task_description,
                result=excluded.result,
                attestation=excluded.attestation
            """,
            (
                node.agent_id,
                node.parent_id,
                node.intent_root,
                node.capability_scope,
                node.capability_token,
                node.spawned_by,
                node.spawned_at,
                node.completed_at,
                node.status.value,
                node.depth,
                node.task_description,
                json.dumps(node.result) if node.result else None,
                json.dumps(node.attestation.to_dict()) if node.attestation else None,
            ),
        )
        self._conn.commit()

    def _persist_delete(self, agent_id: str) -> None:
        if self._conn is None:
            return
        self._conn.execute("DELETE FROM agent_mesh WHERE agent_id=?", (agent_id,))
        self._conn.commit()

    def register_agent(
        self,
        task_description: str,
        capability_scope: str,
        capability_token: str | None = None,
        parent_id: str | None = None,
        intent_root: str | None = None,
        spawned_by: str | None = None,
    ) -> AgentNode:
        now = datetime.now(timezone.utc).isoformat()
        agent_id = new_urn_uuid()
        effective_intent = intent_root or new_urn_uuid()
        parent = self._nodes.get(parent_id) if parent_id else None
        depth = (parent.depth + 1) if parent else 0

        if depth > self._max_depth:
            raise DepthLimitError(f"Agent depth {depth} exceeds max_depth {self._max_depth}")

        node = AgentNode(
            agent_id=agent_id,
            parent_id=parent_id,
            intent_root=effective_intent,
            capability_scope=capability_scope,
            capability_token=capability_token,
            spawned_by=spawned_by,
            spawned_at=now,
            completed_at=None,
            status=AgentStatus.PENDING,
            depth=depth,
            task_description=task_description,
            result=None,
            attestation=None,
        )
        self._nodes[agent_id] = node
        if parent_id and parent_id in self._nodes:
            self._children_of.setdefault(parent_id, set()).add(agent_id)
        self._persist_upsert(node)
        return node

    def transition(self, agent_id: str, status: AgentStatus) -> AgentNode:
        node = self._get(agent_id)
        if status == AgentStatus.COMPLETED or status == AgentStatus.FAILED:
            node.completed_at = datetime.now(timezone.utc).isoformat()
        node.status = status
        self._persist_upsert(node)
        return node

    def attach_attestation(
        self, agent_id: str, spawned_by: str, intent_root: str, capability_token_id: str
    ) -> AgentSpawnAttestation:
        node = self._get(agent_id)
        now = datetime.now(timezone.utc).isoformat()
        attestation = AgentSpawnAttestation(
            attestation_id=new_urn_uuid(),
            agent_id=agent_id,
            spawned_by=spawned_by,
            intent_root=intent_root,
            capability_token_id=capability_token_id,
            spawned_at=now,
            policy_hash="sha256:0000000000000000000000000000000000000000000000000000000000000000",
            signature=f"mesh::{agent_id}::{now}",
        )
        node.attestation = attestation
        self._persist_upsert(node)
        return attestation

    def store_result(self, agent_id: str, result: dict[str, Any]) -> None:
        node = self._get(agent_id)
        node.result = result
        self._persist_upsert(node)

    def get(self, agent_id: str) -> AgentNode | None:
        return self._nodes.get(agent_id)

    def get_children(self, agent_id: str) -> list[AgentNode]:
        child_ids = self._children_of.get(agent_id, set())
        return [self._nodes[cid] for cid in child_ids if cid in self._nodes]

    def lineage(self, agent_id: str) -> list[AgentNode]:
        chain: list[AgentNode] = []
        current = self._nodes.get(agent_id)
        while current:
            chain.insert(0, current)
            if current.parent_id and current.parent_id in self._nodes:
                current = self._nodes[current.parent_id]
            else:
                break
        return chain

    def subgraph(self, agent_id: str) -> list[AgentNode]:
        result: list[AgentNode] = []
        stack = [agent_id]
        while stack:
            current_id = stack.pop()
            node = self._nodes.get(current_id)
            if node:
                result.append(node)
                stack.extend(self._children_of.get(current_id, set()))
        return result

    def list_all(self, status: AgentStatus | None = None) -> list[AgentNode]:
        nodes = list(self._nodes.values())
        if status:
            nodes = [n for n in nodes if n.status == status]
        return sorted(nodes, key=lambda n: n.spawned_at, reverse=True)

    def remove(self, agent_id: str) -> None:
        if agent_id not in self._nodes:
            raise AgentNotFoundError(f"Agent {agent_id} not found")
        children = self._children_of.pop(agent_id, set())
        for child_id in children:
            self.remove(child_id)
        node = self._nodes[agent_id]
        if node.parent_id and node.parent_id in self._children_of:
            self._children_of[node.parent_id].discard(agent_id)
        self._persist_delete(agent_id)
        del self._nodes[agent_id]

    def _get(self, agent_id: str) -> AgentNode:
        node = self._nodes.get(agent_id)
        if not node:
            raise AgentNotFoundError(f"Agent {agent_id} not found")
        return node

    @property
    def max_depth(self) -> int:
        return self._max_depth

    @max_depth.setter
    def max_depth(self, value: int) -> None:
        self._max_depth = value

    @property
    def agent_count(self) -> int:
        return len(self._nodes)

    @property
    def active_agent_count(self) -> int:
        return sum(
            1
            for n in self._nodes.values()
            if n.status in (AgentStatus.PENDING, AgentStatus.RUNNING, AgentStatus.IDLE)
        )
