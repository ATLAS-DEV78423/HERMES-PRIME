from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hermes_prime.contracts import IntentRoot, MemoryClaim, MemoryTier, TrustState
from hermes_prime.secrets import get_signer
from hermes_prime.signing import HMACSigner
from hermes_prime.utils import new_urn_uuid, sha256_text, utc_now_iso


@dataclass
class MemoryAttestation:
    attestation_id: str
    fact_id: str
    intent_root: str
    claim_hash: str
    source: str
    generated_at: str
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "attestation_id": self.attestation_id,
            "fact_id": self.fact_id,
            "intent_root": self.intent_root,
            "claim_hash": self.claim_hash,
            "source": self.source,
            "generated_at": self.generated_at,
            "signature": self.signature,
        }


class ProvenanceLinker:
    def __init__(self, signer: HMACSigner | None = None) -> None:
        self.signer = signer or get_signer("memory-provenance")

    def attest_memory(
        self,
        claim: MemoryClaim,
        intent_root: IntentRoot,
    ) -> MemoryAttestation:
        if claim.intent_root and claim.intent_root != intent_root.intent_root:
            raise ValueError(
                f"claim intent_root {claim.intent_root} does not match provided {intent_root.intent_root}"
            )
        attestation_id = new_urn_uuid()
        claim_hash = sha256_text(claim.claim)
        attestation = MemoryAttestation(
            attestation_id=attestation_id,
            fact_id=claim.fact_id,
            intent_root=intent_root.intent_root,
            claim_hash=claim_hash,
            source=f"provenance:{intent_root.issued_to}",
            generated_at=utc_now_iso(),
            signature="",
        )
        sign_payload = self._signing_payload(attestation, intent_root)
        attestation.signature = self.signer.sign(sign_payload.encode("utf-8"))
        return attestation

    def verify_attestation(
        self,
        attestation: MemoryAttestation,
        intent_root: IntentRoot,
    ) -> bool:
        sign_payload = self._signing_payload(attestation, intent_root)
        return self.signer.verify(sign_payload.encode("utf-8"), attestation.signature)

    def _signing_payload(
        self,
        attestation: MemoryAttestation,
        intent_root: IntentRoot,
    ) -> str:
        return f"{attestation.fact_id}:{attestation.intent_root}:{attestation.claim_hash}:{intent_root.issued_to}:{intent_root.issued_at}"

    def build_claim(
        self,
        claim_text: str,
        source: dict[str, Any],
        intent_root: IntentRoot,
        epistemic_confidence: float = 0.5,
        source_trust: str = "observed",
    ) -> MemoryClaim:
        fact_id = new_urn_uuid()
        return MemoryClaim(
            fact_id=fact_id,
            claim=claim_text,
            source=source,
            epistemic_confidence=epistemic_confidence,
            verification_status="unverified",
            source_trust=source_trust,
            timestamp=utc_now_iso(),
            trust_state=TrustState.UNVERIFIED,
            tier=MemoryTier.QUARANTINE,
            contradictions=[],
            intent_root=intent_root.intent_root,
        )
