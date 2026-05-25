def test_governed_gateway_imports():
    from hermes_prime.gateway.governed_gateway import run_governed_gateway

    assert callable(run_governed_gateway)
