import uuid

import pytest

from hermes_prime.agent.governed_dispatch import GovernedToolDispatcher
from hermes_prime.contracts import (
    ActionType,
    CapabilityToken,
    IntentRoot,
    RiskTier,
    SentinelDecision,
)
from hermes_prime.utils import new_urn_uuid, utc_now_iso


class MockSentinel:
    def evaluate(self, proposal, capability=None):
        return type("EvalResult", (), {
            "decision": SentinelDecision(
                decision_id=new_urn_uuid(),
                timestamp=utc_now_iso(),
                action_id=proposal.action_id,
                permitted=True,
                risk_tier=None,
                policy_rule=None,
                blocking_layer=None,
                denial_reason=None,
            )
        })()

    def register_intent_root(self, intent):
        pass


class MockVault:
    def register_intent_root(self, scope, issued_to):
        return IntentRoot(
            intent_root="urn:uuid:00000000-0000-0000-0000-000000000001",
            scope=scope,
            issued_to=issued_to,
            issued_at=utc_now_iso(),
            expires_at="2026-12-31T00:00:00Z",
            signature="sig",
        )

    def mint_capability(self, capability, scope, actions, risk_tier_ceiling, intent_root, issued_to):
        return CapabilityToken(
            token_id="urn:uuid:00000000-0000-0000-0000-000000000002",
            capability=capability,
            scope=scope,
            actions=actions,
            risk_tier_ceiling=risk_tier_ceiling,
            expires_at="2026-12-31T00:00:00Z",
            intent_root=intent_root,
            issued_to=issued_to,
            issued_at=utc_now_iso(),
            nonce="nonce",
            signature="sig",
        )


def test_governed_dispatch_permits():
    sentinel = MockSentinel()
    vault = MockVault()
    dispatcher = GovernedToolDispatcher(
        sentinel=sentinel,
        vault=vault,
        workspace_root="/tmp/test",
    )

    def sample_tool(query: str) -> str:
        return f"searched: {query}"

    result = dispatcher.dispatch("web_search", {"query": "hello"}, sample_tool)
    assert result == "searched: hello"


def test_governed_dispatch_denies():
    class DenyingSentinel:
        def evaluate(self, proposal, capability=None):
            return type("EvalResult", (), {
                "decision": SentinelDecision(
                    decision_id=new_urn_uuid(),
                    timestamp=utc_now_iso(),
                    action_id=proposal.action_id,
                    permitted=False,
                    risk_tier=None,
                    policy_rule="policy-007",
                    blocking_layer=3,
                    denial_reason="policy violation",
                )
            })()

        def register_intent_root(self, intent):
            pass

    sentinel = DenyingSentinel()
    vault = MockVault()
    dispatcher = GovernedToolDispatcher(
        sentinel=sentinel,
        vault=vault,
        workspace_root="/tmp/test",
    )

    def sample_tool(query: str) -> str:
        return "should not run"

    result = dispatcher.dispatch("web_search", {"query": "hello"}, sample_tool)
    assert "rejected by Sentinel" in result


def test_tool_action_mapping():
    dispatcher = GovernedToolDispatcher(
        sentinel=MockSentinel(),
        vault=MockVault(),
        workspace_root="/tmp/test",
    )

    assert dispatcher._map_tool_to_action("web_search") == ActionType.FILESYSTEM_READ
    assert dispatcher._map_tool_to_action("write_file") == ActionType.FILESYSTEM_WRITE
    assert dispatcher._map_tool_to_action("terminal") == ActionType.EXECUTION_COMMAND
    assert dispatcher._map_tool_to_action("delegate_task") == ActionType.AGENT_SPAWN
    assert dispatcher._map_tool_to_action("unknown_tool") == ActionType.FILESYSTEM_READ
