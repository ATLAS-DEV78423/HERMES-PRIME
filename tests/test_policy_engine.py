from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hermes_prime.contracts import ActionProposal, ActionType, RiskTier
from hermes_prime.utils import new_urn_uuid, utc_now_iso
from infrastructure.policy_engine.engine import PolicyContext, PolicyEngine
from infrastructure.vault.capabilities import CapabilityVault


class PolicyEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Path(self.tmp.name).resolve()
        self.policy = PolicyEngine(PolicyContext(workspace_root=str(self.workspace)))
        self.vault = CapabilityVault()
        self.intent = self.vault.register_intent_root(
            scope=str(self.workspace), issued_to="user:test"
        )
        self.policy.register_intent_root(self.intent)

    def test_read_action_is_permitted_with_matching_token(self) -> None:
        token = self.vault.mint_capability(
            capability="cap:file-read:scoped",
            scope=str(self.workspace),
            actions=["filesystem.read"],
            risk_tier_ceiling=RiskTier.T1,
            intent_root=self.intent.intent_root,
            issued_to="user:test",
        )
        action = ActionProposal(
            action_id=new_urn_uuid(),
            action_type=ActionType.FILESYSTEM_READ,
            scope=str(self.workspace),
            risk_tier=RiskTier.T0,
            intent_root=self.intent.intent_root,
            capability="cap:file-read:scoped",
            proposed_at=utc_now_iso(),
        )
        decision = self.policy.evaluate(action, capability=token)
        self.assertTrue(decision.permitted)
        self.assertIsNone(decision.denial_reason)

    def test_execution_action_is_blocked(self) -> None:
        action = ActionProposal(
            action_id=new_urn_uuid(),
            action_type=ActionType.EXECUTION_COMMAND,
            scope=str(self.workspace),
            risk_tier=RiskTier.T2,
            intent_root=self.intent.intent_root,
            capability="cap:general:scoped",
            proposed_at=utc_now_iso(),
        )
        decision = self.policy.evaluate(action)
        self.assertFalse(decision.permitted)
        self.assertEqual(decision.denial_reason, "execution_command_blocked_until_forge_mvp")

    def test_capability_scope_cannot_exceed_root(self) -> None:
        child_scope = str(self.workspace / "child")
        token = self.vault.mint_capability(
            capability="cap:file-read:scoped",
            scope=child_scope,
            actions=["filesystem.read"],
            risk_tier_ceiling=RiskTier.T1,
            intent_root=self.intent.intent_root,
            issued_to="user:test",
        )
        action = ActionProposal(
            action_id=new_urn_uuid(),
            action_type=ActionType.FILESYSTEM_READ,
            scope=str(self.workspace),
            risk_tier=RiskTier.T0,
            intent_root=self.intent.intent_root,
            capability="cap:file-read:scoped",
            proposed_at=utc_now_iso(),
        )
        decision = self.policy.evaluate(action, capability=token)
        self.assertFalse(decision.permitted)
        self.assertEqual(decision.denial_reason, "scope_exceeds_token")


if __name__ == "__main__":
    unittest.main()
