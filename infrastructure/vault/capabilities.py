from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from hermes_prime.contracts import (
    ActionProposal,
    CapabilityToken,
    IntentRoot,
    RiskTier,
)
from hermes_prime.signing import HMACSigner
from hermes_prime.utils import new_urn_uuid, parse_iso8601, utc_now_iso
from hermes_prime.utils import path_subscope
from infrastructure.trust_store import TrustStore


@dataclass
class IntentRegistry:
    roots: dict[str, IntentRoot] = field(default_factory=dict)

    def register(self, intent_root: IntentRoot) -> None:
        self.roots[intent_root.intent_root] = intent_root

    def get(self, intent_root_id: str) -> IntentRoot | None:
        return self.roots.get(intent_root_id)


class CapabilityVault:
    def __init__(
        self,
        signer: Optional[HMACSigner] = None,
        registry: Optional[IntentRegistry] = None,
        trust_store: Optional[TrustStore] = None,
    ) -> None:
        self.signer = signer or HMACSigner(
            identity="vault:local", secret=b"hermes-prime-vault-secret"
        )
        self.registry = registry or IntentRegistry()
        self.trust_store = trust_store
        self.revoked_tokens: set[str] = set()
        self.revocation_hooks: list[Callable[[str], None]] = []

    def register_intent_root(
        self,
        scope: str,
        issued_to: str,
        ttl_seconds: int = 3600,
        issued_at: str | None = None,
    ) -> IntentRoot:
        issued_at = issued_at or utc_now_iso()
        expires_at = (
            datetime.fromisoformat(issued_at.replace("Z", "+00:00"))
            + timedelta(seconds=ttl_seconds)
        ).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        intent_id = new_urn_uuid()
        payload = {
            "intent_root": intent_id,
            "scope": scope,
            "issued_to": issued_to,
            "issued_at": issued_at,
            "expires_at": expires_at,
        }
        intent_root = IntentRoot(
            intent_root=intent_id,
            scope=scope,
            issued_to=issued_to,
            issued_at=issued_at,
            expires_at=expires_at,
            signature=self.signer.sign_json(payload),
        )
        self.registry.register(intent_root)
        if self.trust_store is not None:
            self.trust_store.store_intent_root(intent_root)
        return intent_root

    def get_intent_root(self, intent_root_id: str) -> IntentRoot | None:
        if intent_root_id in self.registry.roots:
            return self.registry.roots[intent_root_id]
        if self.trust_store is not None:
            intent = self.trust_store.get_intent_root(intent_root_id)
            if intent is not None:
                self.registry.register(intent)
            return intent
        return None

    def mint_capability(
        self,
        capability: str,
        scope: str,
        actions: list[str],
        risk_tier_ceiling: RiskTier,
        intent_root: str,
        issued_to: str,
        ttl_seconds: int = 600,
        issued_at: str | None = None,
        nonce: str | None = None,
    ) -> CapabilityToken:
        if intent_root not in self.registry.roots:
            raise ValueError("unknown intent root")
        if not path_subscope(scope, self.registry.roots[intent_root].scope):
            raise ValueError("capability scope exceeds intent root scope")
        issued_at = issued_at or utc_now_iso()
        expires_at = (
            datetime.fromisoformat(issued_at.replace("Z", "+00:00"))
            + timedelta(seconds=ttl_seconds)
        ).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        nonce = nonce or secrets.token_urlsafe(24)
        token_id = new_urn_uuid()
        payload = {
            "token_id": token_id,
            "capability": capability,
            "scope": scope,
            "actions": actions,
            "risk_tier_ceiling": risk_tier_ceiling.value,
            "expires_at": expires_at,
            "intent_root": intent_root,
            "issued_to": issued_to,
            "issued_at": issued_at,
            "nonce": nonce,
        }
        signature = self.signer.sign_json(payload)
        token = CapabilityToken(
            token_id=token_id,
            capability=capability,
            scope=scope,
            actions=actions,
            risk_tier_ceiling=risk_tier_ceiling,
            expires_at=expires_at,
            intent_root=intent_root,
            issued_to=issued_to,
            issued_at=issued_at,
            nonce=nonce,
            signature=signature,
        )
        if self.trust_store is not None:
            self.trust_store.store_capability_token(token)
        return token

    def verify_token(self, token: CapabilityToken) -> bool:
        if token.token_id in self.revoked_tokens:
            return False
        if self.trust_store is not None:
            stored = self.trust_store.get_capability_token(token.token_id)
            if stored is None or stored.signature != token.signature:
                return False
        intent = self.get_intent_root(token.intent_root)
        if intent is None:
            return False
        if parse_iso8601(token.expires_at) <= parse_iso8601(utc_now_iso()):
            return False
        if token.intent_root != intent.intent_root:
            return False
        if not path_subscope(token.scope, intent.scope):
            return False
        payload = {
            "token_id": token.token_id,
            "capability": token.capability,
            "scope": token.scope,
            "actions": token.actions,
            "risk_tier_ceiling": token.risk_tier_ceiling.value,
            "expires_at": token.expires_at,
            "intent_root": token.intent_root,
            "issued_to": token.issued_to,
            "issued_at": token.issued_at,
            "nonce": token.nonce,
        }
        return self.signer.verify_json(payload, token.signature)

    def revoke_token(self, token_id: str) -> None:
        self.revoked_tokens.add(token_id)
        if self.trust_store is not None:
            self.trust_store.revoke_capability_token(token_id)
        for hook in self.revocation_hooks:
            hook(token_id)

    def validate_for_action(
        self, action: ActionProposal, token: CapabilityToken
    ) -> None:
        if not self.verify_token(token):
            raise ValueError("invalid or expired capability token")
        if action.intent_root != token.intent_root:
            raise ValueError("intent root mismatch")
        if action.capability != token.capability:
            raise ValueError("capability mismatch")
        if action.risk_tier.level > token.risk_tier_ceiling.level:
            raise ValueError("risk tier exceeds token ceiling")
        if not path_subscope(action.scope, token.scope):
            raise ValueError("action scope exceeds token scope")
