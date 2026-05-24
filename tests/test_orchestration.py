from __future__ import annotations

import unittest

from hermes_prime.contracts import (
    ActionType,
    AgentNode,
    AgentSpawnAttestation,
    AgentSpawnRequest,
    AgentStatus,
    RiskTier,
)
from hermes_prime.orch import AgentMesh, CapabilityScoper, Dispatcher, RecursionWatchdog
from hermes_prime.orch.mesh import AgentNotFoundError, DepthLimitError
from hermes_prime.orch.isolation import ScopeViolation
from hermes_prime.utils import new_urn_uuid


class AgentMeshTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mesh = AgentMesh(max_depth=5)

    def test_register_root_agent(self) -> None:
        node = self.mesh.register_agent(
            task_description="root task",
            capability_scope="/workspace",
        )
        self.assertEqual(node.depth, 0)
        self.assertEqual(node.status, AgentStatus.PENDING)
        self.assertIsNone(node.parent_id)
        self.assertEqual(node.task_description, "root task")
        self.assertEqual(self.mesh.agent_count, 1)

    def test_register_child_agent(self) -> None:
        parent = self.mesh.register_agent(
            task_description="parent",
            capability_scope="/workspace",
        )
        child = self.mesh.register_agent(
            task_description="child",
            capability_scope="/workspace/sub",
            parent_id=parent.agent_id,
        )
        self.assertEqual(child.depth, 1)
        self.assertEqual(child.parent_id, parent.agent_id)
        children = self.mesh.get_children(parent.agent_id)
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0].agent_id, child.agent_id)

    def test_depth_limit_exceeded(self) -> None:
        mesh = AgentMesh(max_depth=2)
        n1 = mesh.register_agent(task_description="1", capability_scope="/ws")
        n2 = mesh.register_agent(task_description="2", capability_scope="/ws", parent_id=n1.agent_id)
        n3 = mesh.register_agent(task_description="3", capability_scope="/ws", parent_id=n2.agent_id)
        with self.assertRaises(DepthLimitError):
            mesh.register_agent(task_description="4", capability_scope="/ws", parent_id=n3.agent_id)

    def test_transition_status(self) -> None:
        node = self.mesh.register_agent(task_description="t", capability_scope="/ws")
        self.mesh.transition(node.agent_id, AgentStatus.RUNNING)
        self.assertEqual(self.mesh.get(node.agent_id).status, AgentStatus.RUNNING)

    def test_transition_sets_completed_at(self) -> None:
        node = self.mesh.register_agent(task_description="t", capability_scope="/ws")
        self.mesh.transition(node.agent_id, AgentStatus.COMPLETED)
        n = self.mesh.get(node.agent_id)
        self.assertIsNotNone(n.completed_at)
        self.assertEqual(n.status, AgentStatus.COMPLETED)

    def test_attach_attestation(self) -> None:
        node = self.mesh.register_agent(task_description="t", capability_scope="/ws")
        attestation = self.mesh.attach_attestation(
            agent_id=node.agent_id,
            spawned_by=new_urn_uuid(),
            intent_root=node.intent_root,
            capability_token_id=new_urn_uuid(),
        )
        self.assertIsInstance(attestation, AgentSpawnAttestation)
        self.assertEqual(attestation.agent_id, node.agent_id)
        self.assertEqual(node.attestation.agent_id, node.agent_id)

    def test_store_result(self) -> None:
        node = self.mesh.register_agent(task_description="t", capability_scope="/ws")
        result = {"output": "done", "code": 0}
        self.mesh.store_result(node.agent_id, result)
        self.assertEqual(self.mesh.get(node.agent_id).result, result)

    def test_get_returns_none_for_missing(self) -> None:
        self.assertIsNone(self.mesh.get("urn:uuid:does-not-exist"))

    def test_get_raises_for_missing(self) -> None:
        with self.assertRaises(AgentNotFoundError):
            self.mesh.transition("urn:uuid:does-not-exist", AgentStatus.RUNNING)

    def test_lineage(self) -> None:
        n1 = self.mesh.register_agent(task_description="root", capability_scope="/ws")
        n2 = self.mesh.register_agent(task_description="mid", capability_scope="/ws", parent_id=n1.agent_id)
        n3 = self.mesh.register_agent(task_description="leaf", capability_scope="/ws", parent_id=n2.agent_id)
        lineage = self.mesh.lineage(n3.agent_id)
        self.assertEqual(len(lineage), 3)
        self.assertEqual(lineage[0].agent_id, n1.agent_id)
        self.assertEqual(lineage[1].agent_id, n2.agent_id)
        self.assertEqual(lineage[2].agent_id, n3.agent_id)

    def test_subgraph(self) -> None:
        n1 = self.mesh.register_agent(task_description="root", capability_scope="/ws")
        n2 = self.mesh.register_agent(task_description="c1", capability_scope="/ws", parent_id=n1.agent_id)
        n3 = self.mesh.register_agent(task_description="c2", capability_scope="/ws", parent_id=n1.agent_id)
        n4 = self.mesh.register_agent(task_description="gc", capability_scope="/ws", parent_id=n2.agent_id)
        sg = self.mesh.subgraph(n1.agent_id)
        self.assertEqual(len(sg), 4)
        sg_ids = {n.agent_id for n in sg}
        self.assertIn(n1.agent_id, sg_ids)
        self.assertIn(n2.agent_id, sg_ids)
        self.assertIn(n3.agent_id, sg_ids)
        self.assertIn(n4.agent_id, sg_ids)

    def test_list_all_filters_by_status(self) -> None:
        n1 = self.mesh.register_agent(task_description="t1", capability_scope="/ws")
        n2 = self.mesh.register_agent(task_description="t2", capability_scope="/ws")
        self.mesh.transition(n1.agent_id, AgentStatus.COMPLETED)
        running = self.mesh.list_all(status=AgentStatus.PENDING)
        self.assertEqual(len(running), 1)
        self.assertEqual(running[0].agent_id, n2.agent_id)

    def test_remove_cascades(self) -> None:
        n1 = self.mesh.register_agent(task_description="root", capability_scope="/ws")
        self.mesh.register_agent(task_description="child", capability_scope="/ws", parent_id=n1.agent_id)
        self.mesh.remove(n1.agent_id)
        self.assertEqual(self.mesh.agent_count, 0)

    def test_active_agent_count(self) -> None:
        n1 = self.mesh.register_agent(task_description="t1", capability_scope="/ws")
        n2 = self.mesh.register_agent(task_description="t2", capability_scope="/ws")
        self.mesh.transition(n1.agent_id, AgentStatus.RUNNING)
        self.mesh.transition(n2.agent_id, AgentStatus.COMPLETED)
        self.assertEqual(self.mesh.active_agent_count, 1)


class RecursionWatchdogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mesh = AgentMesh(max_depth=5)
        self.watchdog = RecursionWatchdog(self.mesh)

    def test_check_spawn_root_allows(self) -> None:
        depth = self.watchdog.check_spawn(None)
        self.assertEqual(depth, 0)

    def test_check_spawn_within_limit(self) -> None:
        parent = self.mesh.register_agent(task_description="p", capability_scope="/ws")
        self.mesh.transition(parent.agent_id, AgentStatus.RUNNING)
        node = self.mesh.register_agent(
            task_description="c", capability_scope="/ws", parent_id=parent.agent_id
        )
        self.mesh.transition(node.agent_id, AgentStatus.RUNNING)
        depth = self.watchdog.check_spawn(node.agent_id)
        self.assertEqual(depth, 2)

    def test_prune_overdepth(self) -> None:
        mesh = AgentMesh(max_depth=3)
        n1 = mesh.register_agent(task_description="r", capability_scope="/ws")
        mesh.transition(n1.agent_id, AgentStatus.RUNNING)
        n2 = mesh.register_agent(task_description="c1", capability_scope="/ws", parent_id=n1.agent_id)
        mesh.transition(n2.agent_id, AgentStatus.RUNNING)
        n3 = mesh.register_agent(task_description="c2", capability_scope="/ws", parent_id=n2.agent_id)
        mesh.transition(n3.agent_id, AgentStatus.RUNNING)
        n4 = mesh.register_agent(task_description="c3", capability_scope="/ws", parent_id=n3.agent_id)
        mesh.transition(n4.agent_id, AgentStatus.RUNNING)

        watchdog = RecursionWatchdog(mesh)
        pruned = watchdog.prune_overdepth(max_depth=2)
        self.assertEqual(pruned, 1)
        self.assertEqual(mesh.get(n3.agent_id).status, AgentStatus.RUNNING)
        self.assertEqual(mesh.get(n4.agent_id).status, AgentStatus.KILLED)

    def test_runaway_chain_detected(self) -> None:
        mesh = AgentMesh(max_depth=20)
        prev = None
        for i in range(15):
            n = mesh.register_agent(
                task_description=f"deep-{i}", capability_scope="/ws", parent_id=prev
            )
            prev = n.agent_id
        watchdog = RecursionWatchdog(mesh)
        self.assertTrue(watchdog.runaway_chain_detected(prev, max_consecutive_depth=10))

    def test_terminate_chain(self) -> None:
        n1 = self.mesh.register_agent(task_description="r", capability_scope="/ws")
        self.mesh.transition(n1.agent_id, AgentStatus.RUNNING)
        n2 = self.mesh.register_agent(task_description="c", capability_scope="/ws", parent_id=n1.agent_id)
        self.mesh.transition(n2.agent_id, AgentStatus.RUNNING)
        killed = self.watchdog.terminate_chain(n1.agent_id)
        self.assertEqual(killed, 2)
        self.assertEqual(self.mesh.get(n1.agent_id).status, AgentStatus.KILLED)
        self.assertEqual(self.mesh.get(n2.agent_id).status, AgentStatus.KILLED)


class DispatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mesh = AgentMesh(max_depth=5)
        self.watchdog = RecursionWatchdog(self.mesh)
        self.dispatcher = Dispatcher(mesh=self.mesh, watchdog=self.watchdog)
        self.results: list[str] = []

    def _fake_runner(self, task: str, scope: str, token) -> dict:
        self.results.append(task)
        return {"completed": True, "task": task}

    def test_spawn_root_agent(self) -> None:
        request = AgentSpawnRequest(
            task_description="test task",
            scope="/workspace",
            risk_tier_ceiling=RiskTier.T2,
            parent_agent_id=None,
            max_depth=5,
            capability_actions=[ActionType.FILESYSTEM_READ],
        )
        agent_id = self.dispatcher.spawn(request, spawned_by="test")
        self.assertIsNotNone(agent_id)
        node = self.mesh.get(agent_id)
        self.assertIsNotNone(node)
        self.assertEqual(node.status, AgentStatus.RUNNING)

    def test_spawn_with_runner_completes(self) -> None:
        d = Dispatcher(mesh=self.mesh, watchdog=self.watchdog, runner=self._fake_runner)
        request = AgentSpawnRequest(
            task_description="runner task",
            scope="/workspace",
            risk_tier_ceiling=RiskTier.T2,
            parent_agent_id=None,
            max_depth=5,
            capability_actions=[ActionType.FILESYSTEM_READ],
        )
        agent_id = d.spawn(request, spawned_by="test")
        node = self.mesh.get(agent_id)
        self.assertEqual(node.status, AgentStatus.COMPLETED)
        self.assertEqual(node.result["completed"], True)
        self.assertEqual(len(self.results), 1)

    def test_spawn_with_runner_failure(self) -> None:
        def failing_runner(task, scope, token):
            raise RuntimeError("boom")

        d = Dispatcher(mesh=self.mesh, watchdog=self.watchdog, runner=failing_runner)
        request = AgentSpawnRequest(
            task_description="failing",
            scope="/workspace",
            risk_tier_ceiling=RiskTier.T2,
            parent_agent_id=None,
            max_depth=5,
            capability_actions=[ActionType.FILESYSTEM_READ],
        )
        agent_id = d.spawn(request, spawned_by="test")
        node = self.mesh.get(agent_id)
        self.assertEqual(node.status, AgentStatus.FAILED)
        self.assertIn("error", node.result)

    def test_spawn_depth_limit_enforced(self) -> None:
        mesh = AgentMesh(max_depth=0)
        watchdog = RecursionWatchdog(mesh)
        d = Dispatcher(mesh=mesh, watchdog=watchdog)
        parent = mesh.register_agent(task_description="p", capability_scope="/ws")
        request = AgentSpawnRequest(
            task_description="too deep",
            scope="/ws",
            risk_tier_ceiling=RiskTier.T2,
            parent_agent_id=parent.agent_id,
            max_depth=0,
            capability_actions=[ActionType.FILESYSTEM_READ],
        )
        with self.assertRaises(DepthLimitError):
            d.spawn(request, spawned_by="test")

    def test_kill_agent(self) -> None:
        n1 = self.mesh.register_agent(task_description="t", capability_scope="/ws")
        self.mesh.transition(n1.agent_id, AgentStatus.RUNNING)
        n2 = self.mesh.register_agent(
            task_description="c", capability_scope="/ws", parent_id=n1.agent_id
        )
        self.mesh.transition(n2.agent_id, AgentStatus.RUNNING)
        self.dispatcher.kill(n1.agent_id)
        self.assertEqual(self.mesh.get(n1.agent_id).status, AgentStatus.KILLED)
        self.assertEqual(self.mesh.get(n2.agent_id).status, AgentStatus.KILLED)

    def test_kill_missing_agent_raises(self) -> None:
        with self.assertRaises(Exception):
            self.dispatcher.kill("urn:uuid:does-not-exist")

    def test_list_agents(self) -> None:
        self.mesh.register_agent(task_description="a", capability_scope="/ws")
        self.mesh.register_agent(task_description="b", capability_scope="/ws")
        agents = self.dispatcher.list_agents()
        self.assertEqual(len(agents), 2)

    def test_get_status(self) -> None:
        node = self.mesh.register_agent(task_description="t", capability_scope="/ws")
        status = self.dispatcher.get_status(node.agent_id)
        self.assertEqual(status["agent_id"], node.agent_id)
        self.assertEqual(status["task_description"], "t")

    def test_get_status_missing(self) -> None:
        self.assertIsNone(self.dispatcher.get_status("urn:uuid:nope"))


class CapabilityScoperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scoper = CapabilityScoper(workspace_root="/workspace")

    def _make_token(self, scope: str = "/workspace"):
        from hermes_prime.contracts import CapabilityToken
        return CapabilityToken(
            token_id=new_urn_uuid(),
            capability="agent.spawn",
            scope=scope,
            actions=["filesystem.read", "memory.write"],
            risk_tier_ceiling=RiskTier.T3,
            expires_at="2026-12-31T00:00:00",
            intent_root=new_urn_uuid(),
            issued_to="test",
            issued_at="2026-01-01T00:00:00",
            nonce=new_urn_uuid(),
            signature="sig",
        )

    def test_scope_for_subagent_within_parent(self) -> None:
        parent = self._make_token()
        child = self.scoper.scope_for_subagent(parent, sub_scope="/workspace/sub")
        self.assertEqual(child.scope, "/workspace/sub")
        self.assertEqual(child.risk_tier_ceiling, RiskTier.T2)
        self.assertEqual(child.actions, [ActionType.FILESYSTEM_READ, ActionType.MEMORY_WRITE])

    def test_scope_outside_workspace_raises(self) -> None:
        parent = self._make_token()
        with self.assertRaises(ScopeViolation):
            self.scoper.scope_for_subagent(parent, sub_scope="/outside")

    def test_scope_exceeding_parent_raises(self) -> None:
        parent = self._make_token(scope="/workspace/sub")
        with self.assertRaises(ScopeViolation):
            self.scoper.scope_for_subagent(parent, sub_scope="/workspace")

    def test_verify_action_allowed(self) -> None:
        token = self._make_token()
        self.scoper.verify_action_allowed(token, ActionType.FILESYSTEM_READ, "/workspace/foo")
        with self.assertRaises(ScopeViolation):
            self.scoper.verify_action_allowed(token, ActionType.FILESYSTEM_WRITE, "/workspace/foo")

    def test_verify_action_outside_scope_raises(self) -> None:
        token = self._make_token()
        with self.assertRaises(ScopeViolation):
            self.scoper.verify_action_allowed(token, ActionType.FILESYSTEM_READ, "/outside")

    def test_restrict_actions(self) -> None:
        token = self._make_token()
        restricted = self.scoper.restrict_actions(token, [ActionType.MEMORY_WRITE])
        self.assertEqual(restricted.actions, [ActionType.MEMORY_WRITE])


class AgentNodeContractTests(unittest.TestCase):
    def test_agent_node_requires_urn_uuid(self) -> None:
        with self.assertRaises(ValueError):
            AgentNode(
                agent_id="not-a-uuid",
                parent_id=None,
                intent_root="not-a-uuid",
                capability_scope="/ws",
                capability_token=None,
                spawned_by=None,
                spawned_at="2026-01-01T00:00:00",
                completed_at=None,
                status=AgentStatus.PENDING,
                depth=0,
                task_description="test",
                result=None,
                attestation=None,
            )

    def test_agent_spawn_request_defaults(self) -> None:
        req = AgentSpawnRequest(
            task_description="test",
            scope="/ws",
            risk_tier_ceiling=RiskTier.T2,
            parent_agent_id=None,
            max_depth=5,
            capability_actions=[ActionType.FILESYSTEM_READ],
        )
        self.assertEqual(req.task_description, "test")
        self.assertEqual(req.metadata, {})

    def test_agent_spawn_attestation_requires_urn_uuid(self) -> None:
        with self.assertRaises(ValueError):
            AgentSpawnAttestation(
                attestation_id="bad",
                agent_id="bad2",
                spawned_by="bad3",
                intent_root="bad4",
                capability_token_id="tok",
                spawned_at="2026-01-01T00:00:00",
                policy_hash="h",
                signature="s",
            )

    def test_agent_node_to_dict(self) -> None:
        node = AgentNode(
            agent_id=new_urn_uuid(),
            parent_id=None,
            intent_root=new_urn_uuid(),
            capability_scope="/ws",
            capability_token="tok-1",
            spawned_by="test",
            spawned_at="2026-01-01T00:00:00",
            completed_at=None,
            status=AgentStatus.RUNNING,
            depth=0,
            task_description="test task",
            result=None,
            attestation=None,
        )
        d = node.to_dict()
        self.assertEqual(d["task_description"], "test task")
        self.assertEqual(d["status"], "running")
        self.assertEqual(d["depth"], 0)
        self.assertIsNone(d["attestation"])


if __name__ == "__main__":
    unittest.main()
