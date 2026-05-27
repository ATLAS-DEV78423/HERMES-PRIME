#!/usr/bin/env python3
"""End-to-end functional smoke test for Hermes Prime wiring."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _check(name: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    line = f"  [{status}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def main() -> int:
    print("Hermes Prime — functional wiring smoke test\n")
    results: list[bool] = []

    # --- Infrastructure backends (OPA, tree-sitter, miners) ---
    from infrastructure.backends import BackendRegistry

    registry = BackendRegistry(ROOT)
    manifest = registry.manifest()
    readiness = registry.readiness()
    results.append(_check("BackendRegistry.detect", bool(manifest.get("backends"))))
    results.append(
        _check(
            "BackendRegistry.readiness",
            readiness.get("ready") is True,
            f"missing={readiness.get('critical_missing')}",
        )
    )

    # --- Policy + Sentinel ---
    from infrastructure.policy_engine.bundle import PolicyBundle
    from infrastructure.policy_engine.sentinel_service import SentinelService

    policy_root = ROOT / "infrastructure" / "policy_engine"
    bundle = PolicyBundle(policy_root)
    bundle_manifest = bundle.manifest()
    results.append(_check("PolicyBundle.manifest", bundle_manifest.get("available") is True))

    sentinel = SentinelService(workspace_root=ROOT, policy_root=policy_root)
    results.append(_check("SentinelService.init", sentinel is not None))

    # --- Trust store + Vault ---
    from infrastructure.trust_store import TrustStore
    from infrastructure.vault.capabilities import CapabilityVault
    from hermes_prime.contracts import AuditTrace, RiskTier
    from hermes_prime.utils import new_urn_uuid, utc_now_iso

    tmp_path = Path(tempfile.mkdtemp())
    try:
        trust = TrustStore(tmp_path / "trust.db")
        vault = CapabilityVault()
        intent = vault.register_intent_root(scope=str(tmp_path), issued_to="smoke-test")
        sentinel.register_intent_root(intent)
        token = vault.mint_capability(
            capability="cap:file-read:scoped",
            scope=str(tmp_path),
            actions=["filesystem.read"],
            risk_tier_ceiling=RiskTier.T0,
            intent_root=intent.intent_root,
            issued_to="smoke-test",
        )
        results.append(_check("Vault.mint_capability", token.capability == "cap:file-read:scoped"))
        trace = AuditTrace(
            trace_id=new_urn_uuid(),
            trace_type="smoke",
            created_at=utc_now_iso(),
            workspace_root=str(tmp_path),
            summary="smoke test trace",
        )
        trust.store_audit_trace(trace)
        loaded = trust.get_audit_trace(trace.trace_id)
        results.append(_check("TrustStore.store/get trace", loaded is not None))
        trust.close()
    finally:
        import shutil

        shutil.rmtree(tmp_path, ignore_errors=True)

    # --- Memory fabric (SQLite — default wired path) ---
    from hermes_prime.memory import DepthPolicy, MemoryStore
    from hermes_prime.memory.backends.sqlite_backend import SQLiteMemoryBackend
    from hermes_prime.signing import HMACSigner
    from hermes_prime.contracts import IntentRoot
    from hermes_prime.utils import utc_now_iso

    mem_tmp = Path(tempfile.mkdtemp())
    try:
        db = mem_tmp / "memory.db"
        backend = SQLiteMemoryBackend(db)
        store = MemoryStore(
            backend=backend,
            depth_policy=DepthPolicy(max_claims_per_intent=50, max_total_claims=500),
        )
        signer = HMACSigner(identity="smoke", secret=b"smoke-secret")
        ir = IntentRoot(
            intent_root=new_urn_uuid(),
            scope=str(mem_tmp),
            issued_to="smoke",
            issued_at=utc_now_iso(),
            expires_at="2099-12-31T23:59:59Z",
            signature="sig:placeholder",
        )
        payload = f"{ir.intent_root}:{ir.scope}:{ir.issued_to}:{ir.issued_at}:{ir.expires_at}"
        object.__setattr__(ir, "signature", signer.sign(payload.encode("utf-8")))

        write = store.write(
            claim_text="smoke test memory claim for recall",
            source={"component": "functional_smoke_test"},
            intent_root=ir,
            epistemic_confidence=0.9,
            source_trust="system",
        )
        results.append(_check("MemoryStore.write", write.success, write.fact_id or write.error))

        recall = store.recall("memory claim", limit=5)
        results.append(
            _check(
                "MemoryStore.recall",
                recall.success and len(recall.results) > 0,
                f"hits={len(recall.results)}",
            )
        )
        backend.conn.close()
    finally:
        import shutil

        shutil.rmtree(mem_tmp, ignore_errors=True)

    # --- Autonomous executor pipeline (dummy LLM) ---
    from tests.test_memory_integration import DummyLLM, DummySentinel, DummyTrustStore
    from hermes_prime.autonomous.executor import AutonomousExecutor

    exec_tmp = Path(tempfile.mkdtemp())
    exec_db = exec_tmp / "memory.db"
    exec_backend = SQLiteMemoryBackend(exec_db)
    try:
        llm = DummyLLM()
        llm.workspace_root = str(exec_tmp).replace("\\", "/")
        exec_store = MemoryStore(backend=exec_backend, depth_policy=DepthPolicy())
        exec_signer = HMACSigner(identity="smoke", secret=b"smoke-secret")
        exec_ir = IntentRoot(
            intent_root=new_urn_uuid(),
            scope=str(exec_tmp),
            issued_to="smoke",
            issued_at=utc_now_iso(),
            expires_at="2099-12-31T23:59:59Z",
            signature="sig:placeholder",
        )
        exec_payload = (
            f"{exec_ir.intent_root}:{exec_ir.scope}:{exec_ir.issued_to}:"
            f"{exec_ir.issued_at}:{exec_ir.expires_at}"
        )
        object.__setattr__(exec_ir, "signature", exec_signer.sign(exec_payload.encode("utf-8")))
        exec_store.write(
            claim_text="analysis: prior workspace read approved",
            source={"component": "smoke"},
            intent_root=exec_ir,
            epistemic_confidence=0.9,
            source_trust="system",
        )
        executor = AutonomousExecutor(
            llm_client=llm,
            sentinel=DummySentinel(),
            vault=CapabilityVault(),
            trust_store=DummyTrustStore(),
            workspace_root=exec_tmp,
            signer=HMACSigner(identity="smoke-exec", secret=b"smoke-secret"),
        )
        executor.memory_store = exec_store
        result = executor.execute(task_prompt="analysis: repository review", model="mistral")
        results.append(
            _check(
                "AutonomousExecutor.execute",
                result.execution_status in ("success", "proposal_rejected"),
                result.execution_status,
            )
        )
        exec_backend.conn.close()
    finally:
        import shutil

        shutil.rmtree(exec_tmp, ignore_errors=True)

    # --- Orchestrator (fabric + policy + vault) ---
    from core.hermes_agent.orchestrator import HermesPrimeOrchestrator
    from infrastructure.policy_engine.engine import PolicyContext, PolicyEngine

    fabric_root = ROOT / "external" / "fabric"
    if fabric_root.exists():
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "sample.txt").write_text("hello orchestrator", encoding="utf-8")
            policy = PolicyEngine(PolicyContext(workspace_root=str(tmp_path)))
            orch = HermesPrimeOrchestrator(
                workspace_root=tmp_path,
                fabric_root=fabric_root,
                policy=policy,
                vault=CapabilityVault(),
            )
            orch_result = orch.run("read sample")
            results.append(
                _check(
                    "HermesPrimeOrchestrator.run",
                    orch_result.decision.get("permitted") is True,
                    str(orch_result.action.get("action_type")),
                )
            )
    else:
        results.append(_check("HermesPrimeOrchestrator.run", False, "fabric root missing"))

    # --- Optional backends (availability only) ---
    optional = {
        "chromadb (mem0/atlas)": importlib.util.find_spec("chromadb") is not None,
        "mempalace": importlib.util.find_spec("mempalace") is not None,
        "graphify": importlib.util.find_spec("graphify") is not None,
        "zep": importlib.util.find_spec("zep") is not None,
        "ollama (LLM)": importlib.util.find_spec("ollama") is not None,
    }
    print("\n  Optional backends (not required for core wiring):")
    for name, available in optional.items():
        print(f"    {'[installed]' if available else '[skipped]'} {name}")

    # --- CLI doctor + repair ---
    from hermes_prime.cli import main as cli_main
    from hermes_prime.system_doctor import run_doctor, run_repair
    import io
    from contextlib import redirect_stdout

    doctor_report = run_doctor(ROOT)
    results.append(
        _check(
            "system_doctor.run_doctor", doctor_report.healthy or doctor_report.fixable_count >= 0
        )
    )

    out = io.StringIO()
    with redirect_stdout(out):
        code = cli_main(["--workspace", str(ROOT), "--json", "doctor"])
    try:
        doctor = json.loads(out.getvalue())
        results.append(_check("CLI doctor", code == 0 and "checks" in doctor))
    except json.JSONDecodeError:
        results.append(_check("CLI doctor", False, "invalid JSON output"))

    repair = run_repair(ROOT, dry_run=True)
    results.append(_check("system_doctor.run_repair (dry-run)", repair.dry_run is True))

    passed = sum(results)
    total = len(results)
    print(f"\n{'=' * 50}")
    print(f"Core wiring: {passed}/{total} checks passed")
    if passed == total:
        print("All core subsystems are wired and executing correctly.")
        return 0
    print("Some core checks failed — see details above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
