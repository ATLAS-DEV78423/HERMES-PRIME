"""Governed gateway — patches handle_function_call and launches upstream gateway."""

from __future__ import annotations

import os


def run_governed_gateway(platforms: list[str]) -> int:
    """Start messaging gateway with Sentinel-governed agent sessions.

    Patches upstream handle_function_call to route every tool through
    Sentinel, then delegates to the upstream gateway runner.
    """
    from pathlib import Path
    from hermes_prime.infrastructure_setup import (
        create_sentinel,
        create_vault,
        create_forge,
        create_trust_store,
    )
    from hermes_prime.orch.governed_agent import GovernedAgentWrapper

    workspace = Path.cwd()
    sentinel = create_sentinel(workspace)
    vault = create_vault(workspace)
    forge = create_forge(workspace)
    trust_store = create_trust_store(workspace)

    wrapper = GovernedAgentWrapper(
        sentinel=sentinel,
        vault=vault,
        forge=forge,
        trust_store=trust_store,
        workspace_root=str(workspace),
    )
    wrapper._patch_handle_function_call()

    os.environ.setdefault("HERMES_GATEWAY_PLATFORMS", ",".join(platforms))

    import sys

    sys.argv = ["hermes", "gateway"]

    from gateway.run import main as gateway_main  # type: ignore[import-untyped]

    return gateway_main()


__all__ = ["run_governed_gateway"]
