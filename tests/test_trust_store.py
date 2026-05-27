from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hermes_prime.contracts import (
    AuditTrace,
    CapabilityToken,
    IntentRoot,
    MemoryClaim,
    RiskTier,
    TrustState,
)
from hermes_prime.utils import new_urn_uuid, utc_now_iso
from infrastructure.trust_store import TrustStore, TrustStoreError


class TrustStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = TrustStore(Path(self.tmp.name) / "trust.db")
        self.addCleanup(self.store.close)

    def test_intent_and_token_persist(self) -> None:
        now = utc_now_iso()
        intent = IntentRoot(
            intent_root=new_urn_uuid(),
            scope=self.tmp.name,
            issued_to="user:test",
            issued_at=now,
            expires_at=now,
            signature="sig:test",
        )
        token = CapabilityToken(
            token_id=new_urn_uuid(),
            capability="cap:file-read:scoped",
            scope=self.tmp.name,
            actions=["filesystem.read"],
            risk_tier_ceiling=RiskTier.T1,
            expires_at=now,
            intent_root=intent.intent_root,
            issued_to="user:test",
            issued_at=now,
            nonce="nonce",
            signature="sig:test",
        )
        self.store.store_intent_root(intent)
        self.store.store_capability_token(token)
        self.assertIsNotNone(self.store.get_intent_root(intent.intent_root))
        self.assertIsNotNone(self.store.get_capability_token(token.token_id))

    def test_memory_promotion_enforces_trust_state_machine(self) -> None:
        now = utc_now_iso()
        fact_id = new_urn_uuid()
        claim = MemoryClaim(
            fact_id=fact_id,
            claim="config parses",
            source={"miner": "ast"},
            epistemic_confidence=0.6,
            verification_status="unverified",
            source_trust="heuristic",
            timestamp=now,
            trust_state=TrustState.UNVERIFIED,
        )
        self.store.store_memory_claim(claim)
        self.store.promote_memory_claim(fact_id, TrustState.OBSERVED)
        self.store.promote_memory_claim(fact_id, TrustState.ATTESTED)
        with self.assertRaises(TrustStoreError):
            self.store.promote_memory_claim(fact_id, TrustState.EXECUTABLE)

    def test_contradictory_memory_cannot_be_promoted_to_validated(self) -> None:
        now = utc_now_iso()
        fact_id = new_urn_uuid()
        claim = MemoryClaim(
            fact_id=fact_id,
            claim="config parses",
            source={"miner": "ast"},
            epistemic_confidence=0.6,
            verification_status="unverified",
            source_trust="heuristic",
            timestamp=now,
            trust_state=TrustState.OBSERVED,
            contradictions=[
                {"conflicting_fact_id": new_urn_uuid(), "conflict_type": "logical_negation"}
            ],
        )
        self.store.store_memory_claim(claim)
        claim.trust_state = TrustState.VALIDATED
        with self.assertRaises(TrustStoreError):
            self.store.store_memory_claim(claim)

    def test_audit_trace_persists_and_replays(self) -> None:
        trace = AuditTrace(
            trace_id=new_urn_uuid(),
            trace_type="prompt_flow",
            created_at=utc_now_iso(),
            workspace_root=self.tmp.name,
            intent_root=new_urn_uuid(),
            prompt="read sample",
            summary="trace stored",
        )
        self.store.store_audit_trace(trace)
        loaded = self.store.get_audit_trace(trace.trace_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.trace_type, "prompt_flow")
        self.assertEqual(self.store.list_audit_traces(limit=1)[0].trace_id, trace.trace_id)


if __name__ == "__main__":
    unittest.main()
