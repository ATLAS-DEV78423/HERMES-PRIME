from __future__ import annotations

import os
from dataclasses import dataclass

from hermes_prime.signing import HMACSigner


@dataclass
class SecretConfig:
    identity: str
    secret: bytes
    env_var: str


# Each subsystem gets its own identity/secret pair, overridable via env vars.
SECRET_REGISTRY: dict[str, SecretConfig] = {
    "memory-store": SecretConfig(
        identity="atlas:memory-store",
        secret=b"hermes-prime-memory-store-secret",
        env_var="HERMES_SECRET_MEMORY_STORE",
    ),
    "memory-provenance": SecretConfig(
        identity="atlas:memory-provenance",
        secret=b"hermes-prime-memory-provenance-secret",
        env_var="HERMES_SECRET_MEMORY_PROVENANCE",
    ),
    "autonomous": SecretConfig(
        identity="hermes-autonomous",
        secret=b"default-dev-secret",
        env_var="HERMES_SECRET_AUTONOMOUS",
    ),
    "governance-hooks": SecretConfig(
        identity="hermes-governance-hooks",
        secret=b"hermes-prime-governance",
        env_var="HERMES_SECRET_GOVERNANCE",
    ),
    "governed-agent": SecretConfig(
        identity="hermes-governed-agent",
        secret=b"hermes-prime-governance",
        env_var="HERMES_SECRET_GOVERNED_AGENT",
    ),
    "learning": SecretConfig(
        identity="atlas:learning-engine",
        secret=b"hermes-prime-learning-secret",
        env_var="HERMES_SECRET_LEARNING",
    ),
    "sentinel": SecretConfig(
        identity="sentinel",
        secret=b"default-dev-secret",
        env_var="HERMES_SECRET_SENTINEL",
    ),
    "vault": SecretConfig(
        identity="vault",
        secret=b"default-dev-secret",
        env_var="HERMES_SECRET_VAULT",
    ),
    "miner": SecretConfig(
        identity="miner",
        secret=b"default-dev-secret",
        env_var="HERMES_SECRET_MINER",
    ),
}


def get_signer(subsystem: str) -> HMACSigner:
    cfg = SECRET_REGISTRY.get(subsystem)
    if cfg is None:
        raise ValueError(f"Unknown subsystem: {subsystem}. Known: {list(SECRET_REGISTRY)}")
    env_val = os.environ.get(cfg.env_var)
    if env_val:
        return HMACSigner(identity=cfg.identity, secret=env_val.encode("utf-8"))
    return HMACSigner(identity=cfg.identity, secret=cfg.secret)


def get_secret(subsystem: str) -> bytes:
    cfg = SECRET_REGISTRY.get(subsystem)
    if cfg is None:
        raise ValueError(f"Unknown subsystem: {subsystem}")
    env_val = os.environ.get(cfg.env_var)
    if env_val:
        return env_val.encode("utf-8")
    return cfg.secret
