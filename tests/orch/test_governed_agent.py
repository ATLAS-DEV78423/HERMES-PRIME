import json
from unittest.mock import Mock, patch

import pytest

from hermes_prime.orch.governed_agent import GovernedAgentWrapper


@pytest.fixture
def mock_infrastructure():
    sentinel = Mock()
    sentinel.evaluate.return_value.decision.to_dict.return_value = {
        "permitted": True,
        "blocking_layer": None,
        "denial_reason": None,
    }
    vault = Mock()
    vault.mint_capability.return_value.token_id = "test-token"
    forge = Mock()
    trust_store = Mock()
    return sentinel, vault, forge, trust_store


def test_patches_upstream_handler(mock_infrastructure):
    sentinel, vault, forge, trust_store = mock_infrastructure
    wrapper = GovernedAgentWrapper(sentinel, vault, forge, trust_store)
    with patch("hermes_prime.orch.governed_agent.upstream_agent") as mock_upstream:
        original = mock_upstream.handle_function_call
        wrapper._patch_handle_function_call()
        assert mock_upstream.handle_function_call != original


def test_rejected_tool_returns_error(mock_infrastructure):
    sentinel, vault, forge, trust_store = mock_infrastructure
    sentinel.evaluate.return_value.decision.to_dict.return_value = {
        "permitted": False,
        "blocking_layer": 1,
        "denial_reason": "test: all actions denied",
    }
    wrapper = GovernedAgentWrapper(sentinel, vault, forge, trust_store)
    wrapper._patch_handle_function_call()
    import run_agent as ra

    result = ra.handle_function_call("read", {"path": "/etc"})
    parsed = json.loads(result)
    assert "rejected" in parsed["error"].lower()


def test_approved_tool_calls_original(mock_infrastructure):
    sentinel, vault, forge, trust_store = mock_infrastructure
    wrapper = GovernedAgentWrapper(sentinel, vault, forge, trust_store)
    with patch("hermes_prime.orch.governed_agent.upstream_agent") as mu:
        original_handler = Mock(return_value='{"ok": true}')
        mu.handle_function_call = original_handler
        wrapper._patch_handle_function_call()
        import run_agent as ra

        ra.handle_function_call = mu.handle_function_call
        result = ra.handle_function_call("read", {"path": "test.txt"})
        assert json.loads(result) == {"ok": True}
        assert original_handler.called


def test_audit_trace_stored_on_approval(mock_infrastructure):
    sentinel, vault, forge, trust_store = mock_infrastructure
    wrapper = GovernedAgentWrapper(sentinel, vault, forge, trust_store)
    with patch("hermes_prime.orch.governed_agent.upstream_agent") as mu:
        mu.handle_function_call = Mock(return_value="{}")
        wrapper._patch_handle_function_call()
        import run_agent as ra

        ra.handle_function_call = mu.handle_function_call
        ra.handle_function_call("read", {"path": "test.txt"})
        assert trust_store.store_audit_trace.called
