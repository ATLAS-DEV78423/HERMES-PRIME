from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core.hermes_agent.orchestrator import HermesPrimeOrchestrator
from hermes_prime.contracts import (
    ActionProposal,
    ActionType,
    AuditTrace,
    LifecycleState,
    ProvenanceAttestation,
    RiskTier,
)
from hermes_prime.utils import hash_struct, new_urn_uuid, sha256_bytes, utc_now_iso
from infrastructure.backends import BackendRegistry
from infrastructure.policy_engine.bundle import PolicyBundle
from infrastructure.policy_engine.engine import PolicyContext, PolicyEngine
from infrastructure.policy_engine.sentinel_service import SentinelService
from infrastructure.sandboxed_forge.forge import SandboxedForge
from infrastructure.trust_store import TrustStore
from infrastructure.vault.capabilities import CapabilityVault


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hermes Prime control plane")
    parser.add_argument("--workspace", default=str(Path.cwd()), help="Workspace root")
    parser.add_argument("--fabric-root", default=None, help="Local Fabric repository root")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--prompt", default=None, help="User task prompt")

    subparsers = parser.add_subparsers(dest="command")

    doctor_parser = subparsers.add_parser("doctor", help="Check local backend readiness")
    doctor_parser.add_argument("--strict", action="store_true", help="Exit non-zero if critical backends are missing")

    subparsers.add_parser("inspect", help="Inspect the Sentinel bundle")

    mint_parser = subparsers.add_parser("mint", help="Mint a capability token")
    mint_parser.add_argument("--scope", required=True)
    mint_parser.add_argument("--issued-to", required=True)
    mint_parser.add_argument("--capability", required=True)
    mint_parser.add_argument("--actions", nargs="+", required=True)
    mint_parser.add_argument("--risk-tier-ceiling", default="T1")

    eval_parser = subparsers.add_parser("evaluate", help="Evaluate an action proposal")
    eval_parser.add_argument("--intent-root", required=True)
    eval_parser.add_argument("--token-id", required=True)
    eval_parser.add_argument("--action-type", required=True)
    eval_parser.add_argument("--scope", required=True)
    eval_parser.add_argument("--capability", required=True)
    eval_parser.add_argument("--risk-tier", default="T0")
    eval_parser.add_argument("--proposed-at", default=utc_now_iso())
    eval_parser.add_argument("--parameter", action="append", default=[], help="key=value")

    patch_parser = subparsers.add_parser("patch", help="Stage a governed file mutation")
    patch_parser.add_argument("--intent-root", required=True)
    patch_parser.add_argument("--token-id", required=True)
    patch_parser.add_argument("--path", required=True)
    patch_parser.add_argument("--content", required=True)
    patch_parser.add_argument("--commit", action="store_true")

    replay_parser = subparsers.add_parser("replay", help="Replay an audit trace")
    replay_parser.add_argument("--trace-id", default=None)
    replay_parser.add_argument("--limit", type=int, default=1)

    return parser


def _parse_parameters(values: list[str]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"invalid parameter: {item}")
        key, value = item.split("=", 1)
        params[key] = value
    return params


def _emit(payload: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(payload)


def _humanize_decision(decision: dict[str, Any]) -> str:
    status = "permitted" if decision.get("permitted") else "denied"
    layer = decision.get("blocking_layer")
    reason = decision.get("denial_reason")
    layer_text = f" layer={layer}" if layer is not None else ""
    reason_text = f" reason={reason}" if reason else ""
    return f"Sentinel {status}.{layer_text}{reason_text}"


def main(argv: list[str] | None = None) -> int:
    if argv is not None and "--prompt" not in argv:
        commands = {"doctor", "inspect", "mint", "evaluate", "patch", "replay"}
        non_option_tokens = [token for token in argv if token and not token.startswith("-")]
        if len(non_option_tokens) == 1 and non_option_tokens[0] not in commands:
            argv = list(argv) + ["--prompt", non_option_tokens[0]]
    parser = build_parser()
    args = parser.parse_args(argv)

    workspace = str(Path(args.workspace).resolve())
    workspace_path = Path(workspace)
    fabric_root = args.fabric_root or str(workspace_path / "external" / "fabric")
    policy_root = str(workspace_path / "infrastructure" / "policy_engine")
    trust_path = workspace_path / ".hermes-prime" / "trust.db"
    trust_store = TrustStore(trust_path)
    try:
        policy = PolicyEngine(PolicyContext(workspace_root=workspace))
        vault = CapabilityVault(trust_store=trust_store)
        sentinel = SentinelService(
            workspace_root=workspace,
            policy_root=policy_root,
            trust_store=trust_store,
            policy_engine=policy,
        )

        if args.command == "doctor":
            bundle = PolicyBundle(policy_root)
            readiness = bundle.readiness()
            report = {
                "workspace_root": workspace,
                "policy_root": policy_root,
                "readiness": readiness,
                "trust_store": str(trust_path),
            }
            if args.json:
                _emit(report, True)
            else:
                status = "ready" if readiness["ready"] else "not ready"
                print(f"Hermes Prime is {status}.")
                if readiness["critical_missing"]:
                    print("Missing critical backends: " + ", ".join(readiness["critical_missing"]))
                print(f"Policy bundle: {readiness['bundle']['bundle_root']}")
            return 0 if readiness["ready"] or not args.strict else 1

        if args.command == "inspect":
            bundle = PolicyBundle(policy_root).manifest()
            backends = BackendRegistry(workspace_path).manifest()
            trace = AuditTrace(
                trace_id=new_urn_uuid(),
                trace_type="inspect",
                created_at=utc_now_iso(),
                workspace_root=workspace,
                mutation={"bundle_manifest": bundle, "backend_manifest": backends},
                summary=f"Inspected policy bundle with {len(bundle.get('artifacts', []))} artifacts.",
            )
            trust_store.store_audit_trace(trace)
            if args.json:
                _emit({"bundle": bundle, "backends": backends, "trace_id": trace.trace_id}, True)
            else:
                print(
                    f"Sentinel bundle: {bundle['bundle_root']} ({len(bundle['artifacts'])} artifacts)"
                )
                print(f"Backend preference: {backends['preferred']}")
            return 0

        if args.command == "mint":
            intent = vault.register_intent_root(scope=args.scope, issued_to=args.issued_to)
            sentinel.register_intent_root(intent)
            token = vault.mint_capability(
                capability=args.capability,
                scope=args.scope,
                actions=args.actions,
                risk_tier_ceiling=RiskTier(args.risk_tier_ceiling),
                intent_root=intent.intent_root,
                issued_to=args.issued_to,
            )
            trace = AuditTrace(
                trace_id=new_urn_uuid(),
                trace_type="mint",
                created_at=utc_now_iso(),
                workspace_root=workspace,
                intent_root=intent.intent_root,
                action={
                    "scope": args.scope,
                    "issued_to": args.issued_to,
                    "capability": args.capability,
                    "actions": list(args.actions),
                    "risk_tier_ceiling": args.risk_tier_ceiling,
                },
                mutation={"intent_root": intent.to_dict(), "token": token.to_dict()},
                summary=f"Minted capability {token.capability} for {args.issued_to}.",
            )
            trust_store.store_audit_trace(trace)
            _emit({"intent_root": intent.to_dict(), "token": token.to_dict(), "trace_id": trace.trace_id}, args.json)
            return 0

        if args.command == "evaluate":
            intent = trust_store.get_intent_root(args.intent_root)
            token = trust_store.get_capability_token(args.token_id)
            if intent is None:
                parser.error("unknown intent root")
            if token is None:
                parser.error("unknown capability token")
            if token.intent_root != intent.intent_root:
                parser.error("intent root and token do not match")
            sentinel.register_intent_root(intent)
            if token.capability != args.capability:
                parser.error("capability mismatch")
            action = ActionProposal(
                action_id=new_urn_uuid(),
                action_type=ActionType(args.action_type),
                scope=args.scope,
                risk_tier=RiskTier(args.risk_tier),
                intent_root=intent.intent_root,
                capability=token.capability,
                proposed_at=args.proposed_at,
                parameters=_parse_parameters(args.parameter),
            )
            evaluation = sentinel.evaluate(action, capability=token)
            trace = AuditTrace(
                trace_id=new_urn_uuid(),
                trace_type="evaluation",
                created_at=utc_now_iso(),
                workspace_root=workspace,
                intent_root=intent.intent_root,
                action=action.to_dict(),
                decision=evaluation.to_dict(),
                summary=f"Evaluated {action.action_type.value} and {('permitted' if evaluation.decision.permitted else 'denied')}.",
            )
            trust_store.store_audit_trace(trace)
            if args.json:
                _emit({"evaluation": evaluation.to_dict(), "trace_id": trace.trace_id}, True)
            else:
                print(_humanize_decision(evaluation.decision.to_dict()))
            return 0

        if args.command == "patch":
            intent = trust_store.get_intent_root(args.intent_root)
            token = trust_store.get_capability_token(args.token_id)
            if intent is None:
                parser.error("unknown intent root")
            if token is None:
                parser.error("unknown capability token")
            if token.intent_root != intent.intent_root:
                parser.error("intent root and token do not match")
            sentinel.register_intent_root(intent)
            if token.capability not in {"cap:file-write:scoped", "cap:general:scoped"}:
                parser.error("capability token is not file-write capable")

            path_arg = Path(args.path)
            target = path_arg if path_arg.is_absolute() else (workspace_path / path_arg)
            target = target.resolve()
            try:
                target.relative_to(workspace_path)
            except ValueError:
                parser.error("patch path must stay within the workspace")

            relative_path = target.relative_to(workspace_path).as_posix()
            write_action = ActionProposal(
                action_id=new_urn_uuid(),
                action_type=ActionType.FILESYSTEM_WRITE,
                scope=target.as_posix(),
                risk_tier=RiskTier.T1,
                intent_root=intent.intent_root,
                capability=token.capability,
                proposed_at=utc_now_iso(),
                parameters={"path": relative_path, "content": args.content},
            )
            write_evaluation = sentinel.evaluate(write_action, capability=token)
            forge = SandboxedForge(workspace)

            def authorize(action: ActionProposal):
                return sentinel.evaluate(action, capability=token).decision

            session = forge.start_session(
                intent_root=intent.intent_root,
                capability=token.capability,
                authorizer=authorize,
            )
            session.write_text(relative_path, args.content)
            diff = session.diff(relative_path)
            committed: list[str] = []
            if args.commit:
                committed = session.commit()
                for committed_rel in committed:
                    committed_path = workspace_path / committed_rel
                    if committed_path.exists():
                        provenance = ProvenanceAttestation(
                            attestation_id=new_urn_uuid(),
                            artifact_hash=sha256_bytes(committed_path.read_bytes()),
                            artifact_type="file",
                            generated_by="forge",
                            model_id="forge:local",
                            intent_root=intent.intent_root,
                            parent_attestation_ids=[],
                            input_attestation_ids=[],
                            generated_at=utc_now_iso(),
                            lifecycle_state=LifecycleState.COMMITTED,
                            signature="sig:local",
                        )
                        trust_store.store_provenance_attestation(provenance)
            trace = AuditTrace(
                trace_id=new_urn_uuid(),
                trace_type="patch_flow",
                created_at=utc_now_iso(),
                workspace_root=workspace,
                intent_root=intent.intent_root,
                action=write_action.to_dict(),
                decision=write_evaluation.to_dict(),
                mutation={
                    "target": relative_path,
                    "diff": diff,
                    "committed": committed,
                    "journal": [entry.__dict__ for entry in session.journal.entries],
                },
                summary=f"Patch {relative_path} {'committed' if committed else 'staged'} with Sentinel authorization.",
            )
            trust_store.store_audit_trace(trace)
            payload = {
                "evaluation": write_evaluation.to_dict(),
                "diff": diff,
                "committed": committed,
                "target": relative_path,
                "trace_id": trace.trace_id,
            }
            if args.json:
                _emit(payload, True)
            else:
                print(
                    f"{relative_path}: {'committed' if committed else 'staged'} "
                    f"({ _humanize_decision(write_evaluation.decision.to_dict()) })"
                )
            return 0

        if args.command == "replay":
            if args.trace_id:
                trace = trust_store.get_audit_trace(args.trace_id)
                if trace is None:
                    parser.error("unknown trace id")
                payload = trace.to_dict()
            else:
                traces = trust_store.list_audit_traces(limit=max(args.limit, 1))
                payload = [trace.to_dict() for trace in traces]
            replay_trace = AuditTrace(
                trace_id=new_urn_uuid(),
                trace_type="replay",
                created_at=utc_now_iso(),
                workspace_root=workspace,
                action={"trace_id": args.trace_id, "limit": args.limit},
                mutation={"result_count": len(payload) if isinstance(payload, list) else 1},
                summary=(
                    f"Replayed trace {args.trace_id}" if args.trace_id else f"Listed {args.limit} audit traces"
                ),
            )
            trust_store.store_audit_trace(replay_trace)
            if args.json:
                _emit({"replay": payload, "trace_id": replay_trace.trace_id}, True)
            else:
                if isinstance(payload, list):
                    for trace in payload:
                        print(f"{trace['trace_type']} {trace['trace_id']}: {trace['summary']}")
                else:
                    print(f"{payload['trace_type']} {payload['trace_id']}: {payload['summary']}")
            return 0

        if args.prompt is None:
            parser.error("prompt is required when no subcommand is provided")

        orchestrator = HermesPrimeOrchestrator(
            workspace_root=workspace,
            fabric_root=fabric_root,
            policy=policy,
            vault=vault,
            trust_store=trust_store,
        )
        result = orchestrator.run(args.prompt)
        if args.json:
            _emit(
                {
                    "trace_id": result.trace_id,
                    "backends": BackendRegistry(workspace_path).manifest(),
                    "prompt": result.prompt,
                    "classification": result.classification,
                    "pattern_matches": result.pattern_matches,
                    "augmentation": result.augmentation,
                    "action": result.action,
                    "decision": result.decision,
                    "retrieval": result.retrieval,
                    "summary": result.summary,
                },
                True,
            )
        else:
            backends = BackendRegistry(workspace_path).manifest()
            print(f"Backend preference: {backends['preferred']}")
            print(result.summary)
        return 0
    finally:
        trust_store.close()


if __name__ == "__main__":
    raise SystemExit(main())
