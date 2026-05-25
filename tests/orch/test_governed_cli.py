def test_governed_cli_imports():
    from hermes_prime.orch.governed_cli import run_governed_chat
    assert callable(run_governed_chat)
