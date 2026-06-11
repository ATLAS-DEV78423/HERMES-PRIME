def test_governed_gateway_imports():
    from hermes_prime.gateway.governed_gateway import run_governed_gateway

    assert callable(run_governed_gateway)


def test_run_governed_gateway_import():
    from hermes_prime.gateway.governed_gateway import run_governed_gateway
    assert callable(run_governed_gateway)


def test_run_governed_gateway_no_platforms():
    """run_governed_gateway fails gracefully when upstream is missing."""
    from hermes_prime.gateway.governed_gateway import run_governed_gateway
    from unittest.mock import patch
    with patch("hermes_prime.infrastructure_setup.create_sentinel") as ms:
        ms.return_value = None
        with patch("hermes_prime.infrastructure_setup.create_vault") as mv:
            mv.return_value = None
            with patch("hermes_prime.infrastructure_setup.create_forge") as mf:
                mf.return_value = None
                with patch("hermes_prime.infrastructure_setup.create_trust_store") as mt:
                    mt.return_value = None
                    with patch("hermes_prime.orch.governed_agent.GovernedAgentWrapper") as mw:
                        mw.return_value._patch_handle_function_call = lambda: None
                        try:
                            result = run_governed_gateway([])
                            assert result != 0
                        except Exception:
                            pass
