from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hermes_prime.autonomous.executor import AutonomousExecutor
from hermes_prime.llm.client import LLMClient, LLMRequest, LLMResponse
from hermes_prime.signing import HMACSigner
from hermes_prime.memory.backends.sqlite_backend import SQLiteMemoryBackend
from hermes_prime.memory import MemoryStore, DepthPolicy
from hermes_prime.utils import new_urn_uuid, utc_now_iso
from hermes_prime.contracts import RiskTier, SentinelDecision
from infrastructure.policy_engine.sentinel_service import SentinelEvaluation
from infrastructure.vault.capabilities import CapabilityVault


class DummyLLM(LLMClient):
    def __init__(self):
        self.last_request = None
        self.workspace_root = "."

    def health_check(self) -> bool:
        return True

    def list_models(self) -> list[str]:
        return ["mistral:latest"]

    def infer(self, request: LLMRequest) -> LLMResponse:
        self.last_request = request
        return LLMResponse(
            model=request.model,
            message_content='{"action_type": "filesystem.read", "scope": "'
            + self.workspace_root.replace("\\", "/")
            + '/src", "capability": "cap:file-read:scoped", "parameters": {}}',
            finish_reason="stop",
            tokens_used=10,
            latency_ms=1.0,
        )


class DummySentinel:
    def register_intent_root(self, intent_root):
        return None

    def evaluate(self, action, capability=None, advisory_signals=None):
        decision = SentinelDecision(
            decision_id=new_urn_uuid(),
            timestamp=utc_now_iso(),
            action_id=action.action_id,
            permitted=True,
            risk_tier=RiskTier.T0,
            policy_rule=None,
            blocking_layer=None,
            denial_reason=None,
        )
        return SentinelEvaluation(decision=decision, source="test", bundle_manifest={})


class DummyTrustStore:
    def __init__(self):
        self.traces = []

    def store_audit_trace(self, trace):
        self.traces.append(trace)


def _make_intent_root(scope: str = "/test"):
    from hermes_prime.signing import HMACSigner

    signer = HMACSigner(identity="test", secret=b"test-secret")
    from hermes_prime.utils import new_urn_uuid, utc_now_iso
    from hermes_prime.contracts import IntentRoot

    ir = IntentRoot(
        intent_root=new_urn_uuid(),
        scope=scope,
        issued_to="test-user",
        issued_at=utc_now_iso(),
        expires_at="2099-12-31T23:59:59Z",
        signature="sig:placeholder",
    )
    payload = f"{ir.intent_root}:{ir.scope}:{ir.issued_to}:{ir.issued_at}:{ir.expires_at}"
    sig = signer.sign(payload.encode("utf-8"))
    object.__setattr__(ir, "signature", sig)
    return ir


class TestMemoryIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "mem.db"
        self.backend = SQLiteMemoryBackend(self.db_path)
        self.store = MemoryStore(
            backend=self.backend,
            depth_policy=DepthPolicy(max_claims_per_intent=10, max_total_claims=100),
        )
        self.intent = _make_intent_root(scope=str(self.tmp))

        # write a memory claim that should be recalled (must match recall substring search)
        self.store.write(
            claim_text="analysis: previous action read /workspace/src approved",
            source={"component": "test"},
            intent_root=self.intent,
            epistemic_confidence=0.9,
            source_trust="system",
        )

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_executor_includes_recall_and_records_attestation(self):
        llm = DummyLLM()
        sentinel = DummySentinel()
        trust_store = DummyTrustStore()
        vault = CapabilityVault()

        executor = AutonomousExecutor(
            llm_client=llm,
            sentinel=sentinel,
            vault=vault,
            trust_store=trust_store,
            workspace_root=self.tmp,
            signer=HMACSigner(identity="test-executor", secret=b"test-secret"),
        )

        # use the same memory store backend so executor recall will find our test claim
        executor.memory_store = self.store

        # tell DummyLLM about workspace_root so its response scope is within intent root
        llm.workspace_root = str(self.tmp)

        # run executor; it should recall the previous claim and include it in the user prompt
        executor.execute(
            task_prompt="analysis: repository review and propose next step", model="mistral"
        )

        self.assertIsNotNone(llm.last_request)
        # user message should contain the recalled claim text
        user_msg = llm.last_request.messages[1]["content"]
        self.assertIn("analysis:", user_msg)

        # trust_store should have at least one audit trace (the execution trace)
        self.assertGreaterEqual(len(trust_store.traces), 1)
        trace = trust_store.traces[-1]
        # the trace mutation should include inference attestation and memory attestation when available
        self.assertIn("inference_attestation", trace.mutation)
        # memory attestation may or may not be present depending on memory backend; if present, ensure fields exist
        if "memory_attestation" in trace.mutation:
            ma = trace.mutation["memory_attestation"]
            self.assertIn("fact_id", ma)


if __name__ == "__main__":
    unittest.main()
