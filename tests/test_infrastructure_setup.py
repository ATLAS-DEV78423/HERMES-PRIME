def test_infrastructure_setup_imports():
    from hermes_prime.infrastructure_setup import (
        create_sentinel,
        create_vault,
        create_forge,
        create_trust_store,
    )

    assert callable(create_sentinel)
    assert callable(create_vault)
    assert callable(create_forge)
    assert callable(create_trust_store)
