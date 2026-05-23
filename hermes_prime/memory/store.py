from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hermes_prime.contracts import (
    IntentRoot,
    MemoryClaim,
    MemoryTier,
    TrustState,
    trust_transition_allowed,
)
from hermes_prime.memory.records import MemoryRecord, MemoryType, record_from_claim
from hermes_prime.memory.base import MemoryBackend, MemorySearchResult
from hermes_prime.memory.backends.sqlite_backend import SQLiteMemoryBackend
from hermes_prime.memory.depth import DepthPolicy
from hermes_prime.memory.provenance import MemoryAttestation, ProvenanceLinker
from hermes_prime.signing import HMACSigner
from hermes_prime.utils import new_urn_uuid, utc_now_iso


class MemoryStoreError(RuntimeError):
    pass


@dataclass
class MemoryStoreResult:
    success: bool
    fact_id: str = ""
    attestation: MemoryAttestation | None = None
    error: str = ""
    claim: MemoryClaim | None = None
    record: MemoryRecord | None = None
    results: list[MemorySearchResult] = field(default_factory=list)
    claims: list[MemoryClaim] = field(default_factory=list)
    deleted_count: int = 0
    total_count: int = 0


class MemoryStore:
    def __init__(
        self,
        backend: MemoryBackend | None = None,
        depth_policy: DepthPolicy | None = None,
        provenance_linker: ProvenanceLinker | None = None,
        signer: HMACSigner | None = None,
    ) -> None:
        self.backend = backend or SQLiteMemoryBackend(".hermes-prime/memory.db")
        self.depth_policy = depth_policy or DepthPolicy()
        self.provenance_linker = provenance_linker or ProvenanceLinker(
            signer=signer or HMACSigner(
                identity="atlas:memory-store",
                secret=b"hermes-prime-memory-store-secret",
            )
        )
        self.signer = signer or HMACSigner(
            identity="atlas:memory-store",
            secret=b"hermes-prime-memory-store-secret",
        )

    def write(
        self,
        claim_text: str,
        source: dict[str, Any],
        intent_root: IntentRoot,
        epistemic_confidence: float = 0.5,
        source_trust: str = "observed",
    ) -> MemoryStoreResult:
        current_for_intent = len([
            c for c in self.backend.list_all()
            if c.intent_root == intent_root.intent_root
        ])
        total = self.backend.count()
        allowed, reason = self.depth_policy.check_claim_allowed(
            claim_text, current_for_intent, total
        )
        if not allowed:
            return MemoryStoreResult(success=False, error=reason)

        claim = self.provenance_linker.build_claim(
            claim_text=claim_text,
            source=source,
            intent_root=intent_root,
            epistemic_confidence=epistemic_confidence,
            source_trust=source_trust,
        )
        attestation = self.provenance_linker.attest_memory(claim, intent_root)
        self.backend.store(claim)
        record = record_from_claim(claim, memory_type=MemoryType.EPISODIC)
        return MemoryStoreResult(
            success=True,
            fact_id=claim.fact_id,
            attestation=attestation,
            claim=claim,
            record=record,
            total_count=total + 1,
        )

    def recall(self, query: str, limit: int = 10) -> MemoryStoreResult:
        results = self.backend.search(query, limit=limit)
        return MemoryStoreResult(success=True, results=results)

    def get(self, fact_id: str) -> MemoryStoreResult:
        claim = self.backend.get(fact_id)
        if claim is None:
            return MemoryStoreResult(success=False, error=f"fact {fact_id} not found")
        results = [MemorySearchResult.from_claim(claim)]
        return MemoryStoreResult(success=True, results=results, claim=claim, fact_id=fact_id)

    def list_all(self) -> MemoryStoreResult:
        claims = self.backend.list_all()
        return MemoryStoreResult(
            success=True,
            claims=claims,
            results=[MemorySearchResult.from_claim(c) for c in claims],
            total_count=len(claims),
        )

    def revoke(self, fact_id: str) -> MemoryStoreResult:
        claim = self.backend.get(fact_id)
        if claim is None:
            return MemoryStoreResult(success=False, error=f"fact {fact_id} not found")
        claim.trust_state = TrustState.REVOKED
        self.backend.store(claim)
        return MemoryStoreResult(success=True, fact_id=fact_id, claim=claim)

    def promote(self, fact_id: str, target_state: TrustState = TrustState.VALIDATED) -> MemoryStoreResult:
        claim = self.backend.get(fact_id)
        if claim is None:
            return MemoryStoreResult(success=False, error=f"fact {fact_id} not found")
        current = claim.trust_state if isinstance(claim.trust_state, TrustState) else TrustState(claim.trust_state)
        target = target_state if isinstance(target_state, TrustState) else TrustState(target_state)
        if not trust_transition_allowed(current, target):
            return MemoryStoreResult(
                success=False,
                error=f"invalid trust transition {current.value} -> {target.value}",
            )
        if target in {TrustState.VALIDATED, TrustState.EXECUTABLE} and claim.contradictions:
            return MemoryStoreResult(
                success=False,
                error="contradictory memory claims cannot be promoted",
            )
        if target in {TrustState.VALIDATED, TrustState.EXECUTABLE} and self.depth_policy.authoritative_only_corroborated:
            if claim.epistemic_confidence < 0.8:
                return MemoryStoreResult(
                    success=False,
                    error="cannot promote to authoritative with confidence < 0.8",
                )
        claim.trust_state = target
        if target in {TrustState.VALIDATED, TrustState.EXECUTABLE}:
            claim.tier = MemoryTier.AUTHORITATIVE
        self.backend.store(claim)
        return MemoryStoreResult(success=True, fact_id=fact_id, claim=claim)

    def gc(self, before_timestamp: str | None = None) -> MemoryStoreResult:
        if before_timestamp is None:
            import datetime as dt
            cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=self.depth_policy.gc_retention_days)
            before_timestamp = cutoff.isoformat().replace("+00:00", "Z")
        deleted = self.backend.gc(before_timestamp)
        remaining = self.backend.count()
        return MemoryStoreResult(
            success=True,
            deleted_count=deleted,
            total_count=remaining,
        )
