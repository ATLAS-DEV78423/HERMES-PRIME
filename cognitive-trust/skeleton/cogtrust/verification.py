"""
Verification service.

Stateless query layer that walks attestation chains, checks signatures,
checks revocation status, and returns trust status.

Caches results keyed by (attestation_id, revocation_index_version) so that
revocation invalidates caches automatically (CT-I13).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from cogtrust.attestations import (
    Attestation,
    canonical_payload_for_signing,
)
from cogtrust.lineage import LineageStore
from cogtrust.revocation import RevocationIndex
from cogtrust.signing import verify_with_public_key_b64


class TrustState(str, Enum):
    VALID = "valid"
    EXPIRED = "expired"
    NOT_YET_VALID = "not_yet_valid"
    REVOKED = "revoked"
    DERIVATIVE_REVOKED = "derivative_revoked"
    SIGNATURE_INVALID = "signature_invalid"
    MISSING_PREDECESSOR = "missing_predecessor"
    UNKNOWN = "unknown"


@dataclass
class TrustStatus:
    attestation_id: str
    state: TrustState
    reason: str
    chain_length: int
    checked_at_revocation_version: int
    cache_hit: bool


class Verifier:
    """
    Verification service. Performs chain validation with caching.
    """

    def __init__(
        self,
        lineage: LineageStore,
        revocation: RevocationIndex,
    ) -> None:
        self._lineage = lineage
        self._revocation = revocation
        # Cache: (attestation_id, revocation_version) → TrustStatus
        self._cache: dict[tuple[str, int], TrustStatus] = {}
        self._cache_lock = threading.Lock()

    def verify(self, attestation_id: str) -> TrustStatus:
        """Verify the full chain. Returns TrustStatus."""
        current_version = self._revocation.version()
        cache_key = (attestation_id, current_version)

        # Cache check.
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                # Return cached with cache_hit=True.
                return TrustStatus(
                    attestation_id=cached.attestation_id,
                    state=cached.state,
                    reason=cached.reason,
                    chain_length=cached.chain_length,
                    checked_at_revocation_version=cached.checked_at_revocation_version,
                    cache_hit=True,
                )

        result = self._compute_status(attestation_id, current_version)

        with self._cache_lock:
            self._cache[cache_key] = result

        return result

    def _compute_status(
        self, attestation_id: str, current_version: int
    ) -> TrustStatus:
        # Exists?
        att = self._lineage.get(attestation_id)
        if att is None:
            return TrustStatus(
                attestation_id=attestation_id,
                state=TrustState.UNKNOWN,
                reason="attestation not found in lineage",
                chain_length=0,
                checked_at_revocation_version=current_version,
                cache_hit=False,
            )

        # Revoked directly?
        if self._revocation.is_revoked(attestation_id):
            entry = self._revocation.entry(attestation_id)
            return TrustStatus(
                attestation_id=attestation_id,
                state=(
                    TrustState.DERIVATIVE_REVOKED
                    if entry and entry.derivative
                    else TrustState.REVOKED
                ),
                reason=entry.reason if entry else "revoked",
                chain_length=1,
                checked_at_revocation_version=current_version,
                cache_hit=False,
            )

        # Time bounds.
        now = datetime.now(timezone.utc)
        if att.not_before:
            nb = datetime.fromisoformat(att.not_before)
            if now < nb:
                return TrustStatus(
                    attestation_id=attestation_id,
                    state=TrustState.NOT_YET_VALID,
                    reason=f"not_before is {att.not_before}",
                    chain_length=1,
                    checked_at_revocation_version=current_version,
                    cache_hit=False,
                )
        if att.expires_at:
            exp = datetime.fromisoformat(att.expires_at)
            if now > exp:
                return TrustStatus(
                    attestation_id=attestation_id,
                    state=TrustState.EXPIRED,
                    reason=f"expired at {att.expires_at}",
                    chain_length=1,
                    checked_at_revocation_version=current_version,
                    cache_hit=False,
                )

        # Signature verification.
        if not self._verify_signature(att):
            return TrustStatus(
                attestation_id=attestation_id,
                state=TrustState.SIGNATURE_INVALID,
                reason="signature verification failed",
                chain_length=1,
                checked_at_revocation_version=current_version,
                cache_hit=False,
            )

        # Walk predecessors.
        chain_length = 1
        if att.intent_root_ref:
            intent = self._lineage.get(att.intent_root_ref)
            if intent is None:
                return TrustStatus(
                    attestation_id=attestation_id,
                    state=TrustState.MISSING_PREDECESSOR,
                    reason=f"intent_root {att.intent_root_ref} not in lineage",
                    chain_length=chain_length,
                    checked_at_revocation_version=current_version,
                    cache_hit=False,
                )
            # Check intent root status (must not be revoked or expired).
            intent_status = self._compute_status(
                att.intent_root_ref, current_version
            )
            if intent_status.state != TrustState.VALID:
                return TrustStatus(
                    attestation_id=attestation_id,
                    state=TrustState.DERIVATIVE_REVOKED
                    if intent_status.state
                    in (TrustState.REVOKED, TrustState.DERIVATIVE_REVOKED)
                    else intent_status.state,
                    reason=f"intent_root state: {intent_status.state.value}",
                    chain_length=chain_length + intent_status.chain_length,
                    checked_at_revocation_version=current_version,
                    cache_hit=False,
                )
            chain_length += intent_status.chain_length

        for pred_id in att.predecessor_refs:
            pred_status = self._compute_status(pred_id, current_version)
            if pred_status.state != TrustState.VALID:
                return TrustStatus(
                    attestation_id=attestation_id,
                    state=TrustState.DERIVATIVE_REVOKED
                    if pred_status.state
                    in (TrustState.REVOKED, TrustState.DERIVATIVE_REVOKED)
                    else pred_status.state,
                    reason=f"predecessor {pred_id} state: {pred_status.state.value}",
                    chain_length=chain_length + pred_status.chain_length,
                    checked_at_revocation_version=current_version,
                    cache_hit=False,
                )
            chain_length += pred_status.chain_length

        return TrustStatus(
            attestation_id=attestation_id,
            state=TrustState.VALID,
            reason="chain verified",
            chain_length=chain_length,
            checked_at_revocation_version=current_version,
            cache_hit=False,
        )

    def _verify_signature(self, att: Attestation) -> bool:
        """Verify the attestation's signature against its issuer cert chain."""
        if not att.issuer_cert_chain:
            return False
        public_key_b64 = att.issuer_cert_chain[0]
        payload = canonical_payload_for_signing(att.to_dict())
        return verify_with_public_key_b64(
            public_key_b64, payload, att.signature_value
        )

    def invalidate_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()

    def cache_size(self) -> int:
        with self._cache_lock:
            return len(self._cache)
