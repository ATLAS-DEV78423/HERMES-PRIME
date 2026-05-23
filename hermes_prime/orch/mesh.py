from __future__ import annotations

from datetime import datetime, timezone
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
    def __init__(self, max_depth: int = 5) -> None:
        self._nodes: dict[str, AgentNode] = {}
        self._children_of: dict[str, set[str]] = {}
        self._max_depth = max_depth

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
            raise DepthLimitError(
                f"Agent depth {depth} exceeds max_depth {self._max_depth}"
            )

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
        return node

    def transition(self, agent_id: str, status: AgentStatus) -> AgentNode:
        node = self._get(agent_id)
        if status == AgentStatus.COMPLETED or status == AgentStatus.FAILED:
            node.completed_at = datetime.now(timezone.utc).isoformat()
        node.status = status
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
        return attestation

    def store_result(self, agent_id: str, result: dict[str, Any]) -> None:
        node = self._get(agent_id)
        node.result = result

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
            1 for n in self._nodes.values()
            if n.status in (AgentStatus.PENDING, AgentStatus.RUNNING, AgentStatus.IDLE)
        )
