"""Governed CLI launcher — patches handle_function_call and launches upstream CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def run_governed_chat(
    model: str = "mistral",
    scope: str = ".",
    context: Optional[str] = None,
) -> int:
    """Launch interactive Sentinel-governed chat session.

    Patches the upstream handle_function_call to route every tool
    through Sentinel, then delegates to the upstream Hermes CLI.
    """
    from hermes_prime.infrastructure_setup import (
        create_sentinel,
        create_vault,
        create_forge,
        create_trust_store,
    )
    from hermes_prime.orch.governed_agent import GovernedAgentWrapper

    workspace = Path(scope).resolve()
    sentinel = create_sentinel(workspace)
    vault = create_vault(workspace)
    forge = create_forge(workspace)
    trust_store = create_trust_store(workspace)

    # Patch handle_function_call with Sentinel governance
    wrapper = GovernedAgentWrapper(
        sentinel=sentinel,
        vault=vault,
        forge=forge,
        trust_store=trust_store,
        workspace_root=str(workspace),
    )
    wrapper._patch_handle_function_call()

    # Forward to upstream CLI
    import sys

    sys.argv = ["hermes", "chat", "--model", model]

    from hermes_cli.main import main as upstream_main

    return upstream_main()


__all__ = ["run_governed_chat"]
