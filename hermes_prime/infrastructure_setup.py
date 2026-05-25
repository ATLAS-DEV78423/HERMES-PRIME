"""Shared factories for Hermes Prime infrastructure components.
Used by governed CLI and gateway launchers."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def create_sentinel(workspace: Path) -> Any:
    from infrastructure.policy_engine.sentinel_service import SentinelService
    from infrastructure.policy_engine.engine import PolicyEngine, PolicyContext

    policy = PolicyEngine(PolicyContext(workspace_root=str(workspace)))
    policy_root = str(workspace / "infrastructure" / "policy_engine")
    trust_store = create_trust_store(workspace)
    return SentinelService(
        workspace_root=str(workspace),
        policy_root=policy_root,
        trust_store=trust_store,
        policy_engine=policy,
    )


def create_vault(workspace: Path) -> Any:
    from infrastructure.vault.capabilities import CapabilityVault

    from hermes_prime.infrastructure_setup import create_trust_store

    trust_store = create_trust_store(workspace)
    return CapabilityVault(trust_store=trust_store)


def create_forge(workspace: Path) -> Any:
    from infrastructure.sandboxed_forge.forge import SandboxedForge

    return SandboxedForge(workspace)


def create_trust_store(workspace: Path) -> Any:
    from infrastructure.trust_store import TrustStore

    return TrustStore(workspace / ".hermes-prime" / "trust.db")
