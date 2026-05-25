from unittest.mock import Mock
from hermes_prime.orch.governance_hooks import GovernanceHooks


class TestGovernanceHooks:
    def test_wrap_upstream_command_rejected(self):
        """When Sentinel rejects, the command is blocked."""
        sentinel = Mock()
        sentinel.evaluate.return_value.decision.to_dict.return_value = {
            "permitted": False,
            "blocking_layer": 1,
            "denial_reason": "cron scheduling not permitted",
        }
        vault = Mock()
        vault.mint_capability.return_value.token_id = "test-token"
        trust_store = Mock()

        hooks = GovernanceHooks(sentinel, vault, trust_store, "/test")

        def dummy_cmd(*args, **kwargs):
            return 0

        wrapped = hooks.wrap("cron", dummy_cmd)
        result = wrapped("add", {"schedule": "* * * * *", "command": "rm -rf /"})
        assert result == 1  # blocked
        assert sentinel.evaluate.called

    def test_wrap_upstream_command_approved(self):
        """When Sentinel approves, the command executes normally."""
        sentinel = Mock()
        sentinel.evaluate.return_value.decision.to_dict.return_value = {
            "permitted": True,
            "blocking_layer": None,
            "denial_reason": None,
        }
        vault = Mock()
        vault.mint_capability.return_value.token_id = "test-token"
        trust_store = Mock()

        hooks = GovernanceHooks(sentinel, vault, trust_store, "/test")

        def dummy_cmd(*args, **kwargs):
            return 0

        wrapped = hooks.wrap("tools", dummy_cmd)
        result = wrapped("enable", {"tool": "terminal"})
        assert result == 0  # allowed
        assert trust_store.store_audit_trace.called

    def test_apply_cron_hook(self):
        """apply_cron_hook patches the upstream cron module's add_job."""
        sentinel = Mock()
        sentinel.evaluate.return_value.decision.to_dict.return_value = {
            "permitted": True,
        }
        hooks = GovernanceHooks(sentinel, Mock(), Mock(), "/test")
        mock_cron = Mock()
        mock_cron.add_job = Mock(return_value="ok")
        hooks.apply_cron_hook(mock_cron)
        result = mock_cron.add_job("* * * * *", "echo hello")
        assert result == "ok"
        assert sentinel.evaluate.called
