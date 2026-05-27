from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hermes_prime.contracts import (
    ActionProposal,
    ActionType,
    CapabilityToken,
    IntentRoot,
    RiskTier,
    TrustState,
    trust_transition_allowed,
)
from hermes_prime.utils import new_urn_uuid, utc_now_iso


class ContractTests(unittest.TestCase):
    def test_action_and_capability_contracts_validate(self) -> None:
        now = utc_now_iso()
        with tempfile.TemporaryDirectory() as tmp:
            scope = str(Path(tmp).resolve())
            intent = IntentRoot(
                intent_root=new_urn_uuid(),
                scope=scope,
                issued_to="user:test",
                issued_at=now,
                expires_at=now,
                signature="sig:test",
            )
            action = ActionProposal(
                action_id=new_urn_uuid(),
                action_type=ActionType.FILESYSTEM_READ,
                scope=scope,
                risk_tier=RiskTier.T0,
                intent_root=intent.intent_root,
                capability="cap:file-read:scoped",
                proposed_at=now,
            )
            token = CapabilityToken(
                token_id=new_urn_uuid(),
                capability="cap:file-read:scoped",
                scope=scope,
                actions=["filesystem.read"],
                risk_tier_ceiling=RiskTier.T1,
                expires_at=now,
                intent_root=intent.intent_root,
                issued_to="user:test",
                issued_at=now,
                nonce="nonce",
                signature="sig:test",
            )

            self.assertEqual(action.to_dict()["action_type"], "filesystem.read")
            self.assertEqual(token.to_dict()["risk_tier_ceiling"], "T1")

    def test_trust_state_transitions_are_bounded(self) -> None:
        self.assertTrue(trust_transition_allowed(TrustState.UNVERIFIED, TrustState.OBSERVED))
        self.assertTrue(trust_transition_allowed(TrustState.ATTESTED, TrustState.VALIDATED))
        self.assertFalse(trust_transition_allowed(TrustState.EXECUTABLE, TrustState.ATTESTED))

    def test_new_action_types_are_defined(self) -> None:
        self.assertEqual(ActionType.WEB_SEARCH.value, "web.search")
        self.assertEqual(ActionType.BROWSER_NAVIGATE.value, "browser.navigate")
        self.assertEqual(ActionType.VOICE_SPEAK.value, "voice.speak")
        self.assertEqual(ActionType.VISION_ANALYZE.value, "vision.analyze")
        self.assertEqual(ActionType.CODE_EXECUTE.value, "code.execute")
        self.assertEqual(ActionType.SKILLS_READ.value, "skills.read")
        self.assertEqual(ActionType.KANBAN_READ.value, "kanban.read")
        self.assertEqual(ActionType.MCP_CALL.value, "mcp.call")
        self.assertEqual(ActionType.SESSION_SEARCH.value, "session.search")
        all_values = [e.value for e in ActionType]
        self.assertEqual(len(all_values), len(set(all_values)))


if __name__ == "__main__":
    unittest.main()
