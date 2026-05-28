from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Add upstream hermes-agent to sys.path so we can import AIAgent, HermesCLI, gateway, etc.
_HERMES_AGENT_PATH = str(Path(__file__).resolve().parent.parent / "external" / "hermes-agent")
if _HERMES_AGENT_PATH not in sys.path:
    sys.path.insert(0, _HERMES_AGENT_PATH)

from core.hermes_agent.orchestrator import HermesPrimeOrchestrator
from hermes_prime.contracts import (
    ActionProposal,
    ActionType,
    AuditTrace,
    LifecycleState,
    ProvenanceAttestation,
    RiskTier,
)
from hermes_prime.learning.outcome import OutcomeStore
from hermes_prime.learning.registry import LearningRegistry
from hermes_prime.learning.engine import LearningEngine
from hermes_prime.memory import DepthPolicy, MemoryStore
from hermes_prime.memory.backends.sqlite_backend import SQLiteMemoryBackend
from hermes_prime.memory.backends.mempalace_backend import MemPalaceBackend
from hermes_prime.utils import new_urn_uuid, sha256_bytes, utc_now_iso
from infrastructure.backends import BackendRegistry
from infrastructure.policy_engine.bundle import PolicyBundle
from infrastructure.policy_engine.engine import PolicyContext, PolicyEngine
from infrastructure.policy_engine.sentinel_service import SentinelService
from infrastructure.sandboxed_forge.forge import SandboxedForge
from infrastructure.trust_store import TrustStore
from infrastructure.vault.capabilities import CapabilityVault

known_hp_commands = {
    "graphify",
    "repair",
    "inspect",
    "mint",
    "evaluate",
    "patch",
    "replay",
    "models",
    "run",
    "agents",
    "hp-dashboard",
    "tui",
    "learn",
    "brain",
    "hp-doctor",
    "hp-memory",
    "chat",
    "gateway",
    "skills",
    "sessions",
    "todo",
    "tools",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hermes Prime control plane")
    parser.add_argument("--workspace", default=str(Path.cwd()), help="Workspace root")
    parser.add_argument("--fabric-root", default=None, help="Local Fabric repository root")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--prompt", default=None, help="User task prompt")
    parser.add_argument(
        "--model", default="mistral", help="LLM model to use (for --prompt with --autonomous)"
    )
    parser.add_argument(
        "--autonomous", action="store_true", help="Use autonomous LLM-driven execution"
    )
    parser.add_argument(
        "--memory-backend",
        default="sqlite",
        choices=["sqlite", "mempalace", "graphify"],
        help="Memory backend to use (default: sqlite)",
    )
    parser.add_argument(
        "--memory-backend-config",
        default=None,
        help="Backend config path (palace dir for mempalace)",
    )

    subparsers = parser.add_subparsers(dest="command")

    # Phase 8: Graphify commands
    graphify_parser = subparsers.add_parser("graphify", help="Graphify knowledge graph commands")
    graphify_sub = graphify_parser.add_subparsers(dest="graphify_command")

    g_build = graphify_sub.add_parser("build", help="Build knowledge graph from workspace")
    g_build.add_argument("--target", default=None, help="Target directory to analyze")

    g_query = graphify_sub.add_parser("query", help="Query the knowledge graph")
    g_query.add_argument("query", help="Query text")
    g_query.add_argument("--limit", type=int, default=10)
    g_query.add_argument("--depth", type=int, default=2, help="BFS depth for subgraph extraction")

    graphify_sub.add_parser("status", help="Check graphify availability and graph status")

    g_import_parser = graphify_sub.add_parser(
        "import", help="Import graphify graph into KnowledgeGraph"
    )
    g_import_parser.add_argument("--graph-path", default=None, help="Path to graph.json")

    doctor_parser = subparsers.add_parser(
        "hp-doctor",
        help="Diagnose Hermes Prime installation and workspace health",
    )
    doctor_parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any ERROR-level issues are found",
    )

    repair_parser = subparsers.add_parser(
        "repair",
        help="Repair auto-fixable Hermes Prime workspace issues",
    )
    repair_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be fixed without making changes",
    )
    repair_parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild corrupted SQLite databases (backs up first)",
    )

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

    # Phase 2: Memory Fabric
    memory_parser = subparsers.add_parser("hp-memory", help="Memory fabric commands")
    memory_sub = memory_parser.add_subparsers(dest="memory_command")

    mem_write = memory_sub.add_parser("write", help="Write a fact to memory")
    mem_write.add_argument("--claim", required=True, help="The fact/belief text")
    mem_write.add_argument("--intent-root", required=True, help="Intent root URN")
    mem_write.add_argument(
        "--confidence", type=float, default=0.5, help="Epistemic confidence (0-1)"
    )
    mem_write.add_argument("--source", default="cli", help="Source label")
    mem_write.add_argument("--source-trust", default="direct", help="Source trust level")

    mem_recall = memory_sub.add_parser("recall", help="Search memory by query")
    mem_recall.add_argument("--query", required=True, help="Search query text")
    mem_recall.add_argument("--limit", type=int, default=10, help="Max results")

    memory_sub.add_parser("list", help="List all memory claims")

    mem_revoke = memory_sub.add_parser("revoke", help="Revoke a memory claim")
    mem_revoke.add_argument("--fact-id", required=True, help="Fact URN to revoke")

    mem_gc = memory_sub.add_parser("gc", help="Garbage collect old memory claims")
    mem_gc.add_argument("--before", default=None, help="ISO8601 cutoff timestamp")

    # Phase 1: LLM Runtime Integration
    models_parser = subparsers.add_parser("models", help="List available local LLM models")
    models_parser.add_argument("--provider", choices=["ollama", "vllm"], default="ollama")

    run_parser = subparsers.add_parser("run", help="Execute autonomous task (LLM-driven)")
    run_parser.add_argument("--task", required=True, help="Task prompt for LLM")
    run_parser.add_argument("--model", default="mistral", help="LLM model name")
    run_parser.add_argument("--scope", default=None, help="Scope for filesystem access")

    # Phase 3: Agent Orchestration
    agents_parser = subparsers.add_parser("agents", help="Agent orchestration commands")
    agents_sub = agents_parser.add_subparsers(dest="agent_command")

    agents_list = agents_sub.add_parser("list", help="List all agents")
    agents_list.add_argument(
        "--status",
        default=None,
        choices=[
            "idle",
            "running",
            "completed",
            "failed",
            "killed",
            "pending",
        ],
        help="Filter by status",
    )

    agents_spawn = agents_sub.add_parser("spawn", help="Spawn a new sub-agent")
    agents_spawn.add_argument("--task", required=True, help="Task description for the agent")
    agents_spawn.add_argument("--scope", required=True, help="Capability scope")
    agents_spawn.add_argument("--parent", default=None, help="Parent agent ID")
    agents_spawn.add_argument("--risk-tier", default="T2", help="Risk tier ceiling")
    agents_spawn.add_argument(
        "--actions", nargs="*", default=["filesystem.read", "memory.write"], help="Allowed actions"
    )

    agents_kill = agents_sub.add_parser("kill", help="Kill an agent and its descendants")
    agents_kill.add_argument("--agent-id", required=True, help="Agent URN to kill")

    # Learning Loop commands
    learn_parser = subparsers.add_parser("learn", help="Learning loop commands")
    learn_sub = learn_parser.add_subparsers(dest="learn_command")

    learn_reflect = learn_sub.add_parser("reflect", help="Run learning loop reflection")
    learn_reflect.add_argument(
        "--min-outcomes", type=int, default=5, help="Minimum outcomes required for reflection"
    )

    learn_sub.add_parser("status", help="Show learning loop status")

    learn_patterns = learn_sub.add_parser("patterns", help="List learned patterns")
    learn_patterns.add_argument(
        "--type", dest="pattern_type", default=None, help="Filter by pattern type"
    )
    learn_patterns.add_argument(
        "--min-confidence", type=float, default=0.0, help="Minimum confidence filter"
    )
    learn_patterns.add_argument("--limit", type=int, default=20, help="Max patterns to show")

    learn_forget = learn_sub.add_parser("forget", help="Remove a learned pattern")
    learn_forget.add_argument("--pattern-id", required=True, help="Pattern ID to remove")

    learn_sub.add_parser("outcomes", help="Show execution outcome summary")

    learn_sub.add_parser("metrics", help="Show learning loop metrics")

    # Brain / Neural Network commands
    brain_parser = subparsers.add_parser("brain", help="Neural brain network commands")
    brain_sub = brain_parser.add_subparsers(dest="brain_command")

    brain_write = brain_sub.add_parser("write", help="Write a note to the brain")
    brain_write.add_argument("--title", required=True, help="Note title")
    brain_write.add_argument("--content", required=True, help="Note content")
    brain_write.add_argument(
        "--type",
        dest="node_type",
        default="observation",
        choices=["topic", "problem", "solution", "observation", "pattern", "decision", "concept"],
    )
    brain_write.add_argument("--tags", default=None, help="Comma-separated tags")
    brain_write.add_argument("--link-to", default=None, help="Comma-separated node IDs to link to")

    brain_search = brain_sub.add_parser("search", help="Search brain nodes")
    brain_search.add_argument("--query", required=True, help="Search query")
    brain_search.add_argument(
        "--type",
        dest="node_type",
        default=None,
        choices=["topic", "problem", "solution", "observation", "pattern", "decision", "concept"],
    )
    brain_search.add_argument("--limit", type=int, default=20)

    brain_problem = brain_sub.add_parser("problem", help="Track a problem and solution")
    brain_problem.add_argument("--title", required=True, help="Problem title")
    brain_problem.add_argument("--description", required=True, help="Problem description")
    brain_problem.add_argument("--context", default=None, help="Context")
    brain_problem.add_argument("--solution-title", default=None, help="Solution title (optional)")
    brain_problem.add_argument(
        "--solution-desc", default=None, help="Solution description (optional)"
    )

    brain_sub.add_parser("status", help="Show brain health and metrics")
    brain_maintenance = brain_sub.add_parser("maintenance", help="Run brain maintenance")
    brain_maintenance.add_argument("--dry-run", action="store_true", help="Show what would be done")
    brain_maintenance.add_argument("--max-age", type=float, default=90.0, help="Max age in days")
    brain_maintenance.add_argument(
        "--min-confidence", type=float, default=0.2, help="Min confidence"
    )

    brain_export = brain_sub.add_parser("export", help="Export brain as Obsidian vault")
    brain_export.add_argument("--output", default="./brain-vault", help="Output directory")

    brain_path = brain_sub.add_parser("path", help="Find path between two nodes")
    brain_path.add_argument("--from-id", required=True, help="Source node ID")
    brain_path.add_argument("--to-id", required=True, help="Target node ID")

    brain_link = brain_sub.add_parser("link", help="Manually link two nodes")
    brain_link.add_argument("--source", required=True, help="Source node ID")
    brain_link.add_argument("--target", required=True, help="Target node ID")
    brain_link.add_argument(
        "--type",
        dest="edge_type",
        default="relates_to",
        choices=[
            "solves",
            "causes",
            "relates_to",
            "prerequisite",
            "contradicts",
            "extends",
            "references",
            "produces",
            "blocks",
            "enables",
        ],
    )

    brain_sub.add_parser("unsolved", help="List unsolved problems")

    # Phase 4: Elite Terminal UI
    subparsers.add_parser("hp-dashboard", help="Launch Textual live dashboard")

    tui_parser = subparsers.add_parser("tui", help="Terminal UI components")
    tui_sub = tui_parser.add_subparsers(dest="tui_command")

    tui_sub.add_parser("logo", help="Display HERMES-PRIME logo")
    tui_sub.add_parser("console", help="Display operator console")
    tui_sub.add_parser("telemetry", help="Display telemetry header")
    tui_sub.add_parser("boot", help="Run boot sequence animation")

    # Phase 5: Interactive chat and gateway
    chat_parser = subparsers.add_parser(
        "chat",
        help="Start interactive Sentinel-governed chat session",
    )
    chat_parser.add_argument("--model", default="mistral", help="LLM model name")
    chat_parser.add_argument("--scope", default=".", help="Workspace scope path")
    chat_parser.add_argument("--context", help="Initial system context override")

    gw_parser = subparsers.add_parser(
        "gateway",
        help="Start messaging gateway (Slack, Discord, Telegram)",
    )
    gw_parser.add_argument(
        "--platforms",
        default="slack",
        help="Comma-separated platform list (slack, discord, telegram)",
    )

    # Agent CLI commands
    skills_parser = subparsers.add_parser("skills", help="Manage agent skills")
    skills_sub = skills_parser.add_subparsers(dest="skills_command")

    skills_list = skills_sub.add_parser("list", help="List all skills")
    skills_list.add_argument("--query", default=None, help="Search query")

    skills_view = skills_sub.add_parser("view", help="View a skill")
    skills_view.add_argument("name", help="Skill name")

    skills_create = skills_sub.add_parser("create", help="Create a new skill")
    skills_create.add_argument("--name", required=True, help="Skill name")
    skills_create.add_argument("--content", required=True, help="Skill content/code")
    skills_create.add_argument("--language", default="python", help="Language")
    skills_create.add_argument("--description", default="", help="Description")
    skills_create.add_argument("--tags", default=None, help="Comma-separated tags")

    skills_delete = skills_sub.add_parser("delete", help="Delete a skill")
    skills_delete.add_argument("name", help="Skill name")

    sessions_parser = subparsers.add_parser("sessions", help="Browse and search sessions")
    sessions_sub = sessions_parser.add_subparsers(dest="sessions_command")

    sessions_sub.add_parser("list", help="List all sessions")

    sessions_search = sessions_sub.add_parser("search", help="Search sessions")
    sessions_search.add_argument("query", help="Search query")

    sessions_view = sessions_sub.add_parser("view", help="View session messages")
    sessions_view.add_argument("session_id", help="Session ID")

    todo_parser = subparsers.add_parser("todo", help="Task planning and tracking")
    todo_sub = todo_parser.add_subparsers(dest="todo_command")

    todo_create = todo_sub.add_parser("create", help="Create a task")
    todo_create.add_argument("--title", required=True, help="Task title")
    todo_create.add_argument("--priority", default="medium", choices=["high", "medium", "low"])
    todo_create.add_argument("--subtasks", default=None, help="Comma-separated subtasks")

    todo_sub.add_parser("list", help="List all tasks")

    todo_complete = todo_sub.add_parser("complete", help="Mark task done")
    todo_complete.add_argument("--task-id", required=True, help="Task ID")

    todo_remove = todo_sub.add_parser("remove", help="Remove a task")
    todo_remove.add_argument("--task-id", required=True, help="Task ID")

    tools_parser = subparsers.add_parser("tools", help="List available agent tools")
    tools_parser.add_argument("--search", default=None, help="Search for tools")

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
    from hermes_prime.recovery import install_signal_handlers

    install_signal_handlers()
    import importlib.util as _iu

    if _iu.find_spec("hermes_cli") is not None:
        import sys as _sys

        print(
            "! conflicting `hermes` CLI: both hermes-prime and hermes-agent are installed.",
            file=_sys.stderr,
            flush=True,
        )
        print(
            "! Use `hermes-prime` instead of `hermes` to ensure this package runs.",
            file=_sys.stderr,
            flush=True,
        )

    if argv is not None and "--prompt" not in argv and "--autonomous" not in argv:
        non_option_tokens = [token for token in argv if token and not token.startswith("-")]
        if len(non_option_tokens) == 1 and non_option_tokens[0] not in known_hp_commands:
            argv = list(argv) + ["--prompt", non_option_tokens[0]]
    parser = build_parser()
    args, _ = parser.parse_known_args(argv)
    cmd = vars(args).get("command")

    workspace = str(Path(args.workspace if hasattr(args, "workspace") else ".").resolve())
    workspace_path = Path(workspace)
    fabric_root = args.fabric_root or str(workspace_path / "external" / "fabric")
    policy_root = str(workspace_path / "infrastructure" / "policy_engine")
    trust_path = workspace_path / ".hermes-prime" / "trust.db"
    trust_store = TrustStore(trust_path)
    policy = PolicyEngine(PolicyContext(workspace_root=workspace))
    vault = CapabilityVault(trust_store=trust_store)
    sentinel = SentinelService(
        workspace_root=workspace,
        policy_root=policy_root,
        trust_store=trust_store,
        policy_engine=policy,
    )

    if not cmd:
        if argv and isinstance(argv, list) and any(a in argv for a in ("--prompt", "--autonomous")):
            cmd = "__prompt__"
        else:
            if _iu.find_spec("hermes_prime.orch.governance_hooks") is not None:
                try:
                    from hermes_prime.orch.governance_hooks import GovernanceHooks

                    hooks = GovernanceHooks(sentinel, vault, trust_store, workspace)
                    if argv and isinstance(argv, list):
                        _first = argv[0]
                        if _first == "cron":
                            try:
                                import cron.scheduler as _cs

                                hooks.apply_cron_hook(_cs)
                            except ImportError:
                                pass
                        elif _first == "tools":
                            try:
                                import hermes_cli.tools_config as _tc

                                if hasattr(_tc, "toggle_tool"):
                                    _tc.toggle_tool = hooks.wrap("tools", _tc.toggle_tool)
                            except ImportError:
                                pass
                        elif _first == "skills":
                            try:
                                import hermes_cli.skills_config as _sc

                                if hasattr(_sc, "install_skill"):
                                    _sc.install_skill = hooks.wrap("skills", _sc.install_skill)
                            except ImportError:
                                pass
                except ImportError:
                    print("warning: governance_hooks found but failed to import", file=sys.stderr)

            try:
                import hermes_cli.main as upstream_main
            except ImportError:
                print(
                    "hermes: upstream hermes-agent not available. Check external/hermes-agent/ path."
                )
                return 1
            return upstream_main.main()

    def handle_hp_command(args: argparse.Namespace) -> int:
        try:
            if args.command == "hp-doctor":
                from hermes_prime.system_doctor import format_doctor_text, run_doctor

                doctor_report = run_doctor(workspace_path)
                memory_path = workspace_path / ".hermes-prime" / "memory.db"
                payload = doctor_report.to_dict()
                payload["trust_store"] = str(trust_path)
                payload["memory_backend"] = str(memory_path)
                payload["policy_root"] = policy_root
                if args.json:
                    _emit(payload, True)
                else:
                    print(format_doctor_text(doctor_report))
                if args.strict and not doctor_report.healthy:
                    return 1
                return 0

            if args.command == "repair":
                from hermes_prime.system_doctor import format_repair_text, run_repair

                repair_report = run_repair(
                    workspace_path,
                    dry_run=args.dry_run,
                    force_db_reset=args.force,
                )
                payload = repair_report.to_dict()
                if not args.dry_run:
                    from hermes_prime.system_doctor import run_doctor

                    payload["post_repair"] = run_doctor(workspace_path).to_dict()
                if args.json:
                    _emit(payload, True)
                else:
                    print(format_repair_text(repair_report))
                    if not args.dry_run and not payload.get("post_repair", {}).get("healthy", True):
                        print("\nSome issues remain. Re-run: hermes doctor")
                failed = [a for a in repair_report.actions if a.applied and not a.success]
                return 1 if failed else 0

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
                    _emit(
                        {"bundle": bundle, "backends": backends, "trace_id": trace.trace_id}, True
                    )
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
                _emit(
                    {
                        "intent_root": intent.to_dict(),
                        "token": token.to_dict(),
                        "trace_id": trace.trace_id,
                    },
                    args.json,
                )
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
                        f"({_humanize_decision(write_evaluation.decision.to_dict())})"
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
                        f"Replayed trace {args.trace_id}"
                        if args.trace_id
                        else f"Listed {args.limit} audit traces"
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
                        print(
                            f"{payload['trace_type']} {payload['trace_id']}: {payload['summary']}"
                        )
                return 0

            # Phase 2: Memory Fabric commands
            if args.command == "hp-memory":
                if args.memory_backend == "mempalace":
                    palace_path = args.memory_backend_config or str(
                        workspace_path / ".hermes-prime" / "palace"
                    )
                    memory_store = MemoryStore(
                        backend=MemPalaceBackend(palace_path=palace_path),
                        depth_policy=DepthPolicy(),
                    )
                elif args.memory_backend == "graphify":
                    from hermes_prime.memory.backends.graphify_backend import GraphifyBackend

                    memory_store = MemoryStore(
                        backend=GraphifyBackend(workspace_path=workspace),
                        depth_policy=DepthPolicy(),
                    )
                else:
                    memory_store = MemoryStore(
                        backend=SQLiteMemoryBackend(
                            args.memory_backend_config
                            or workspace_path / ".hermes-prime" / "memory.db"
                        ),
                        depth_policy=DepthPolicy(),
                    )
                mem_cmd = args.memory_command
                if mem_cmd == "write":
                    intent = trust_store.get_intent_root(args.intent_root)
                    if intent is None:
                        parser.error(f"unknown intent root: {args.intent_root}")
                    result = memory_store.write(
                        claim_text=args.claim,
                        source={
                            "source": args.source,
                            "command": "memory.write",
                            "workspace": workspace,
                        },
                        intent_root=intent,
                        epistemic_confidence=min(max(args.confidence, 0.0), 1.0),
                        source_trust=args.source_trust,
                    )
                    trace = AuditTrace(
                        trace_id=new_urn_uuid(),
                        trace_type="memory_write",
                        created_at=utc_now_iso(),
                        workspace_root=workspace,
                        intent_root=args.intent_root,
                        action={"claim": args.claim, "confidence": args.confidence},
                        decision={"success": result.success},
                        mutation={
                            "fact_id": result.fact_id,
                            "attestation": result.attestation.to_dict()
                            if result.attestation
                            else None,
                        },
                        summary=f"Memory write: {args.claim[:60]}...",
                    )
                    trust_store.store_audit_trace(trace)
                    if args.json:
                        _emit(
                            {
                                "success": result.success,
                                "fact_id": result.fact_id,
                                "attestation": result.attestation.to_dict()
                                if result.attestation
                                else None,
                                "trace_id": trace.trace_id,
                            },
                            True,
                        )
                    else:
                        if result.success:
                            print(f"Memory written: {result.fact_id}")
                        else:
                            print(f"Memory write failed: {result.error}")
                    return 0 if result.success else 1

                elif mem_cmd == "recall":
                    result = memory_store.recall(args.query, limit=args.limit)
                    trace = AuditTrace(
                        trace_id=new_urn_uuid(),
                        trace_type="memory_recall",
                        created_at=utc_now_iso(),
                        workspace_root=workspace,
                        action={"query": args.query, "limit": args.limit},
                        mutation={"result_count": len(result.results)},
                        summary=f"Memory recall: {args.query[:60]}... ({len(result.results)} results)",
                    )
                    trust_store.store_audit_trace(trace)
                    if args.json:
                        _emit(
                            {
                                "query": args.query,
                                "results": [r.__dict__ for r in result.results],
                                "trace_id": trace.trace_id,
                            },
                            True,
                        )
                    else:
                        if not result.results:
                            print("No matching memory claims found.")
                        else:
                            print(f"\nMemory Recall: {args.query}")
                            print(f"{'=' * 60}")
                            for r in result.results:
                                print(f"  [{r.tier}] {r.fact_id}")
                                print(f"  Claim: {r.claim[:120]}")
                                print(f"  Confidence: {r.epistemic_confidence:.2f}")
                                print(f"  Trust: {r.source_trust} | State: {r.trust_state}")
                                print()
                    return 0

                elif mem_cmd == "list":
                    result = memory_store.list_all()
                    trace = AuditTrace(
                        trace_id=new_urn_uuid(),
                        trace_type="memory_list",
                        created_at=utc_now_iso(),
                        workspace_root=workspace,
                        mutation={"claim_count": result.total_count},
                        summary=f"Listed {result.total_count} memory claims",
                    )
                    trust_store.store_audit_trace(trace)
                    if args.json:
                        _emit(
                            {
                                "claims": [c.to_dict() for c in result.claims],
                                "count": result.total_count,
                                "trace_id": trace.trace_id,
                            },
                            True,
                        )
                    else:
                        print(f"\nMemory Claims ({result.total_count} total)")
                        print(f"{'=' * 60}")
                        for c in result.claims:
                            tier = c.tier.value if hasattr(c.tier, "value") else c.tier
                            state = (
                                c.trust_state.value
                                if hasattr(c.trust_state, "value")
                                else c.trust_state
                            )
                            print(f"  [{tier}] [{state}] {c.fact_id}")
                            print(f"  {c.claim[:120]}")
                            print()
                    return 0

                elif mem_cmd == "revoke":
                    result = memory_store.revoke(args.fact_id)
                    trace = AuditTrace(
                        trace_id=new_urn_uuid(),
                        trace_type="memory_revoke",
                        created_at=utc_now_iso(),
                        workspace_root=workspace,
                        action={"fact_id": args.fact_id},
                        decision={"success": result.success},
                        summary=f"Memory revoke: {args.fact_id}",
                    )
                    trust_store.store_audit_trace(trace)
                    if args.json:
                        _emit(
                            {
                                "success": result.success,
                                "fact_id": args.fact_id,
                                "trace_id": trace.trace_id,
                            },
                            True,
                        )
                    else:
                        if result.success:
                            print(f"Memory claim revoked: {args.fact_id}")
                        else:
                            print(f"Revoke failed: {result.error}")
                    return 0 if result.success else 1

                elif mem_cmd == "gc":
                    result = memory_store.gc(before_timestamp=args.before)
                    trace = AuditTrace(
                        trace_id=new_urn_uuid(),
                        trace_type="memory_gc",
                        created_at=utc_now_iso(),
                        workspace_root=workspace,
                        mutation={
                            "deleted_count": result.deleted_count,
                            "remaining": result.total_count,
                        },
                        summary=f"Memory GC: {result.deleted_count} deleted, {result.total_count} remaining",
                    )
                    trust_store.store_audit_trace(trace)
                    if args.json:
                        _emit(
                            {
                                "deleted": result.deleted_count,
                                "remaining": result.total_count,
                                "trace_id": trace.trace_id,
                            },
                            True,
                        )
                    else:
                        print(
                            f"Memory GC: {result.deleted_count} deleted, {result.total_count} remaining"
                        )
                    return 0
                else:
                    parser.error("unknown memory command")
                return 0

            # Phase 1: models command
            if args.command == "models":
                try:
                    from hermes_prime.llm.ollama_adapter import OllamaClient
                    from hermes_prime.llm.vllm_adapter import VLLMClient

                    if args.provider == "ollama":
                        client = OllamaClient()
                        health = client.health_check()
                        if not health:
                            print("Ollama is not running. Start it with: ollama serve")
                            return 1
                        models = client.list_models()
                    else:
                        client = VLLMClient()
                        health = client.health_check()
                        if not health:
                            print("vLLM endpoint is not reachable.")
                            return 1
                        models = client.list_models()

                    if args.json:
                        _emit({"provider": args.provider, "models": models}, True)
                    else:
                        if models:
                            print(f"\n{args.provider.upper()} Models:")
                            for model in models:
                                print(f"  - {model}")
                        else:
                            print(f"No models available from {args.provider}")
                    return 0
                except ImportError:
                    print(
                        "LLM libraries not installed. Install with: pip install hermes-prime[llm]"
                    )
                    return 1
                except Exception as e:
                    print(f"Error listing models: {e}")
                    return 1

            # Phase 4: Elite Terminal UI
            if args.command == "hp-dashboard":
                try:
                    from hermes_prime.tui.dashboard import HermesDashboard

                    dash = HermesDashboard(use_textual=True)
                    return dash.run()
                except Exception as e:
                    print(f"Dashboard unavailable: {e}")
                    return 1

            if args.command == "tui":
                from hermes_prime.tui.banner import HERMES_PRIME_LOGO
                from hermes_prime.tui.components import (
                    OperatorConsole,
                    TelemetryHeader,
                )
                from hermes_prime.tui.animations import boot_sequence

                if args.tui_command == "logo":
                    print(HERMES_PRIME_LOGO)
                    return 0

                if args.tui_command == "console":
                    console = OperatorConsole()
                    print(console.render())
                    return 0

                if args.tui_command == "telemetry":
                    telemetry = TelemetryHeader()
                    print(telemetry.render())
                    return 0

                if args.tui_command == "boot":
                    boot_sequence(clear=lambda: print("\033[2J\033[H", end=""))
                    return 0

                parser.error("unknown tui command")
                return 1

            # Learning Loop commands
            if args.command == "learn":
                outcome_store = OutcomeStore(workspace_path / ".hermes-prime" / "outcomes.db")
                registry = LearningRegistry(
                    workspace_path / ".hermes-prime" / "learned_patterns.json"
                )
                memory_store = MemoryStore(
                    backend=SQLiteMemoryBackend(workspace_path / ".hermes-prime" / "memory.db"),
                    depth_policy=DepthPolicy(),
                )
                engine = LearningEngine(
                    outcome_store=outcome_store,
                    registry=registry,
                    memory_store=memory_store,
                )

                if args.learn_command == "reflect":
                    result = engine.reflect(min_outcomes=args.min_outcomes)
                    if args.json:
                        _emit(result, True)
                    else:
                        if result.get("reflected"):
                            print(
                                f"Reflection complete: {result['patterns_created']} patterns created"
                            )
                            print(f"Reviewed {result['total_outcomes_reviewed']} outcomes")
                            m = result.get("metrics", {})
                            print(f"Approval rate: {m.get('approval_rate', 0):.1%}")
                            print(f"Parse rate: {m.get('parse_rate', 0):.1%}")
                        else:
                            print(f"No reflection: {result.get('reason', 'unknown')}")
                    return 0

                elif args.learn_command == "status":
                    status = engine.status()
                    if args.json:
                        _emit(status, True)
                    else:
                        outcomes = status.get("outcomes", {})
                        patterns = status.get("learned_patterns", {})
                        print("\nLearning Loop Status")
                        print(f"{'=' * 60}")
                        print(f"Total executions tracked: {outcomes.get('total', 0)}")
                        print(f"Approval rate: {outcomes.get('approval_rate', 0):.1%}")
                        print(f"Parse rate: {outcomes.get('parse_rate', 0):.1%}")
                        print(f"Learned patterns: {patterns.get('total_patterns', 0)}")
                        print(f"By type: {patterns.get('by_type', {})}")
                        print(
                            f"Ready to learn: {'yes' if status.get('ready_to_learn') else 'no (need 5+ outcomes)'}"
                        )
                    return 0

                elif args.learn_command == "patterns":
                    patterns = registry.list_patterns(
                        pattern_type=args.pattern_type,
                        min_confidence=args.min_confidence,
                        limit=args.limit,
                    )
                    if args.json:
                        _emit(
                            {"patterns": [p.to_dict() for p in patterns], "count": len(patterns)},
                            True,
                        )
                    else:
                        if not patterns:
                            print("No learned patterns found.")
                        else:
                            print(f"\nLearned Patterns ({len(patterns)})")
                            print(f"{'=' * 60}")
                            for p in patterns:
                                print(
                                    f"  [{p.pattern_type}] {p.pattern_id[:16]}... (confidence: {p.confidence:.2f})"
                                )
                                print(f"  {p.content[:120]}")
                                print(
                                    f"  Applied: {p.application_count}x | Success: {p.success_rate:.0%}"
                                )
                                if p.tags:
                                    print(f"  Tags: {', '.join(p.tags)}")
                                print()
                    return 0

                elif args.learn_command == "forget":
                    success = registry.remove(args.pattern_id)
                    if args.json:
                        _emit({"removed": success, "pattern_id": args.pattern_id}, True)
                    else:
                        if success:
                            print(f"Pattern {args.pattern_id} removed.")
                        else:
                            print(f"Pattern {args.pattern_id} not found.")
                    return 0 if success else 1

                elif args.learn_command == "outcomes":
                    metrics = outcome_store.get_metrics()
                    recent = outcome_store.get_recent(limit=10)
                    if args.json:
                        _emit({"metrics": metrics, "recent": [o.to_dict() for o in recent]}, True)
                    else:
                        print("\nExecution Outcomes")
                        print(f"{'=' * 60}")
                        print(f"Total: {metrics.get('total', 0)}")
                        print(f"Approved: {metrics.get('approved', 0)}")
                        print(f"Rejected by Sentinel: {metrics.get('rejected_by_sentinel', 0)}")
                        print(f"Parse failures: {metrics.get('parse_failures', 0)}")
                        print(f"Approval rate: {metrics.get('approval_rate', 0):.1%}")
                        print(f"Avg latency: {metrics.get('avg_latency_ms', 0)}ms")
                        print(f"Avg tokens: {metrics.get('avg_tokens', 0)}")
                        if metrics.get("blocking_layer_distribution"):
                            print(f"Blocking layers: {metrics['blocking_layer_distribution']}")
                        print("\nRecent outcomes:")
                        for o in recent:
                            status = "✓" if o.approved else "✗"
                            print(f"  [{status}] {o.action_type:20s} {o.task_prompt[:50]}")
                    return 0

                elif args.learn_command == "metrics":
                    outcome_metrics = outcome_store.get_metrics()
                    registry_metrics = registry.get_metrics()
                    payload = {"outcomes": outcome_metrics, "patterns": registry_metrics}
                    if args.json:
                        _emit(payload, True)
                    else:
                        print("\nLearning Metrics")
                        print(f"{'=' * 60}")
                        print(f"Outcomes tracked: {outcome_metrics.get('total', 0)}")
                        print(f"Patterns learned: {registry_metrics.get('total_patterns', 0)}")
                        print(
                            f"Avg pattern confidence: {registry_metrics.get('avg_confidence', 0):.3f}"
                        )
                    return 0

                else:
                    parser.error("unknown learn command")
                return 0

            # Brain / Neural Network commands
            if args.command == "brain":
                from hermes_prime.brain import (
                    NeuralGraph,
                    BrainJournal,
                    AutoLinker,
                    BrainMaintenanceAgent,
                    NodeType,
                    EdgeType,
                )

                brain_db = workspace_path / ".hermes-prime" / "brain.db"
                graph = NeuralGraph(brain_db)
                journal = BrainJournal(graph)
                linker = AutoLinker(graph)
                maintenance = BrainMaintenanceAgent(graph, linker)

                if args.brain_command == "write":
                    tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
                    type_map = {
                        "topic": NodeType.TOPIC,
                        "problem": NodeType.PROBLEM,
                        "solution": NodeType.SOLUTION,
                        "observation": NodeType.OBSERVATION,
                        "pattern": NodeType.PATTERN,
                        "decision": NodeType.DECISION,
                        "concept": NodeType.CONCEPT,
                    }
                    ntype = type_map.get(args.node_type, NodeType.OBSERVATION)
                    node = graph.add_node(ntype, args.title, args.content, tags=tags)
                    link_ids = [x.strip() for x in args.link_to.split(",")] if args.link_to else []
                    for lid in link_ids:
                        graph.add_edge(node.node_id, lid, EdgeType.RELATES_TO)
                    created = linker.link_new_node(node.node_id)
                    if args.json:
                        _emit(
                            {
                                "node_id": node.node_id,
                                "links_created": created,
                                "node": node.to_dict(),
                            },
                            True,
                        )
                    else:
                        print(f"Brain node written: {node.node_id[:16]}...")
                        print(f"  Title: {node.title}")
                        print(f"  Type: {node.node_type.value}")
                        print(f"  Auto-links created: {created}")
                    return 0

                elif args.brain_command == "search":
                    ntype_enum = NodeType(args.node_type) if args.node_type else None
                    ntypes = [ntype_enum] if ntype_enum else None
                    results = graph.search_nodes(args.query, node_types=ntypes, limit=args.limit)
                    if args.json:
                        _emit(
                            {"query": args.query, "results": [r.to_dict() for r in results]}, True
                        )
                    else:
                        if not results:
                            print(f"No brain nodes matching '{args.query}'")
                        else:
                            print(f"\nBrain Search: '{args.query}' ({len(results)} results)")
                            print(f"{'=' * 60}")
                            for r in results:
                                edges = graph.get_node_edges(r.node_id)
                                print(f"  [{r.node_type.value}] {r.title}")
                                print(
                                    f"    ID: {r.node_id[:16]}... | Confidence: {r.confidence:.2f} | Links: {len(edges)}"
                                )
                                print(f"    {r.content[:100]}")
                                print()
                    return 0

                elif args.brain_command == "problem":
                    problem = journal.write_problem(
                        args.title, args.description, context=args.context
                    )
                    linker.link_new_node(problem.node_id)
                    print(f"Problem recorded: {problem.node_id[:16]}...")
                    if args.solution_title and args.solution_desc:
                        solution = journal.write_solution(
                            args.solution_title,
                            args.solution_desc,
                            problem.node_id,
                        )
                        linker.link_problem_to_solution(problem.node_id, solution.node_id)
                        print(f"Solution recorded: {solution.node_id[:16]}...")
                    return 0

                elif args.brain_command == "status":
                    health = maintenance.get_health_report()
                    metrics = graph.get_metrics()
                    if args.json:
                        _emit({"health": health, "metrics": metrics}, True)
                    else:
                        print("\nBrain Health")
                        print(f"{'=' * 60}")
                        print(f"Total nodes: {health['total_nodes']}")
                        print(f"Total connections: {health['total_edges']}")
                        print(f"Health score: {health['health_score']:.3f}")
                        print(f"Unsolved problems: {health['unsolved_problems']}")
                        print(f"Orphaned nodes: {health['orphaned_nodes']}")
                        print(f"Low confidence: {health['low_confidence_nodes']}")
                        print(f"Old unused: {health['old_unused_nodes']}")
                        if health.get("by_type"):
                            print("\nBy type:")
                            for t, c in sorted(health["by_type"].items()):
                                print(f"  {t}: {c}")
                    return 0

                elif args.brain_command == "maintenance":
                    report = maintenance.run_maintenance(
                        dry_run=args.dry_run,
                        max_age_days=args.max_age,
                        min_confidence=args.min_confidence,
                    )
                    if args.json:
                        _emit(report, True)
                    else:
                        print("\nBrain Maintenance")
                        print(f"{'=' * 60}")
                        print(f"Pruned nodes: {report['pruned_nodes']}")
                        print(f"Merged duplicates: {report['merged_nodes']}")
                        print(f"Consolidated orphans: {report['consolidated_orphans']}")
                        print(f"Pruned edges: {report['pruned_edges']}")
                        print(f"Remaining nodes: {report['remaining_nodes']}")
                        print(f"Remaining edges: {report['remaining_edges']}")
                        print(f"Dry run: {report['dry_run']}")
                    return 0

                elif args.brain_command == "export":
                    result = journal.export_obsidian_vault(args.output)
                    if args.json:
                        _emit(result, True)
                    else:
                        print(f"Brain exported to {result['vault_path']}")
                        print(f"  {result['notes_exported']} notes")
                        print(f"  {result['links_exported']} connections")
                    return 0

                elif args.brain_command == "path":
                    path = graph.find_shortest_path(args.from_id, args.to_id)
                    if args.json:
                        _emit({"from": args.from_id, "to": args.to_id, "path": path}, True)
                    else:
                        if path:
                            print(f"Path ({len(path) - 1} hops):")
                            for i, nid in enumerate(path):
                                node = graph.get_node(nid)
                                name = node.title if node else nid[:16]
                                arrow = " → " if i < len(path) - 1 else ""
                                print(f"  {i}. {name}{arrow}")
                        else:
                            print("No path found between these nodes.")
                    return 0

                elif args.brain_command == "link":
                    edge = graph.add_edge(
                        args.source,
                        args.target,
                        EdgeType(args.edge_type),
                        weight=1.0,
                    )
                    if args.json:
                        _emit({"edge_id": edge.edge_id if edge else None}, True)
                    else:
                        if edge:
                            print(
                                f"Linked: {args.source[:16]}... → {args.target[:16]}... ({args.edge_type})"
                            )
                        else:
                            print("Failed to create link (may already exist).")
                    return 0

                elif args.brain_command == "unsolved":
                    unsolved = journal.get_problems_unsolved()
                    if args.json:
                        _emit({"unsolved_problems": [p.to_dict() for p in unsolved]}, True)
                    else:
                        if not unsolved:
                            print("No unsolved problems!")
                        else:
                            print(f"\nUnsolved Problems ({len(unsolved)})")
                            print(f"{'=' * 60}")
                            for p in unsolved:
                                sol_count = len(journal.get_solutions_for_problem(p.node_id))
                                print(f"  {p.title}")
                                print(f"    ID: {p.node_id[:16]}... | Solutions tried: {sol_count}")
                                print(f"    {p.content[:100]}")
                                print()
                    return 0

                else:
                    parser.error("unknown brain command")
                return 0

            # Phase 3: Agent Orchestration commands
            if args.command == "agents":
                from hermes_prime.orch import AgentMesh, Dispatcher, RecursionWatchdog
                from hermes_prime.orch.mesh import DepthLimitError
                from hermes_prime.contracts import AgentSpawnRequest

                mesh = AgentMesh(max_depth=5)
                watchdog = RecursionWatchdog(mesh)
                dispatcher = Dispatcher(mesh=mesh, watchdog=watchdog)

                if args.agent_command == "list":
                    agents = dispatcher.list_agents(status=args.status)
                    if args.json:
                        _emit({"agents": agents, "count": len(agents)}, True)
                    else:
                        print(f"\nAgents ({len(agents)} total)")
                        print(f"{'=' * 60}")
                        for a in agents:
                            depth_mark = "(root)" if a["depth"] == 0 else f"depth={a['depth']}"
                            print(f"  [{a['status']}] {a['agent_id'][:16]}... {depth_mark}")
                            print(f"  Task: {a['task_description'][:60]}")
                            print(f"  Scope: {a['capability_scope']}")
                            print()
                    return 0

                elif args.agent_command == "spawn":
                    request = AgentSpawnRequest(
                        task_description=args.task,
                        scope=args.scope,
                        risk_tier_ceiling=RiskTier(args.risk_tier),
                        parent_agent_id=args.parent,
                        max_depth=mesh.max_depth,
                        capability_actions=[ActionType(a) for a in args.actions],
                    )
                    try:
                        agent_id = dispatcher.spawn(request, spawned_by="cli")
                    except DepthLimitError as e:
                        print(f"Failed: {e}")
                        return 1

                    agent_info = dispatcher.get_status(agent_id)
                    if args.json:
                        _emit({"agent_id": agent_id, "agent": agent_info}, True)
                    else:
                        print(f"Agent spawned: {agent_id}")
                        print(f"  Task: {args.task}")
                        print(f"  Scope: {args.scope}")
                        print(f"  Depth: {agent_info['depth'] if agent_info else '?'}")
                    return 0

                elif args.agent_command == "kill":
                    try:
                        dispatcher.kill(args.agent_id)
                        agent_info = dispatcher.get_status(args.agent_id)
                        if args.json:
                            _emit(
                                {
                                    "killed": args.agent_id,
                                    "status": agent_info["status"] if agent_info else "unknown",
                                },
                                True,
                            )
                        else:
                            print(f"Agent {args.agent_id} killed.")
                    except Exception as e:
                        print(f"Failed: {e}")
                        return 1
                    return 0

                else:
                    parser.error("unknown agent command")
                return 0

            # Phase 1: run command (autonomous execution)
            if args.command == "run":
                try:
                    from hermes_prime.llm.ollama_adapter import OllamaClient
                    from hermes_prime.autonomous.executor import AutonomousExecutor

                    client = OllamaClient()
                    if not client.health_check():
                        print("Ollama is not running. Start it with: ollama serve")
                        return 1

                    executor = AutonomousExecutor(
                        llm_client=client,
                        sentinel=sentinel,
                        vault=vault,
                        trust_store=trust_store,
                        workspace_root=workspace,
                        forge=None,
                    )
                    result = executor.execute(
                        task_prompt=args.task,
                        model=args.model,
                        scope=args.scope,
                    )

                    payload = {
                        "execution_id": result.execution_id,
                        "status": result.execution_status,
                        "trace_id": result.trace_id,
                        "task": result.task_prompt,
                        "proposal": result.proposal.to_dict() if result.proposal else None,
                        "decision": result.sentinel_decision,
                        "inference": result.inference_attestation.to_dict()
                        if result.inference_attestation
                        else None,
                        "summary": result.summary,
                    }

                    if args.json:
                        _emit(payload, True)
                    else:
                        print(f"\n{'=' * 60}")
                        print(f"Autonomous Execution: {result.task_prompt}")
                        print(f"{'=' * 60}")
                        if result.proposal:
                            print(f"Proposed Action: {result.proposal.action_type.value}")
                            print(f"Scope: {result.proposal.scope}")
                            print(f"Risk Tier: {result.proposal.risk_tier.value}")
                        print(f"Status: {result.execution_status}")
                        if result.error_message:
                            print(f"Error: {result.error_message}")
                        if result.inference_attestation:
                            print(
                                f"Inference Latency: {result.inference_attestation.latency_ms:.0f}ms"
                            )
                            print(f"Tokens Used: {result.inference_attestation.tokens_used}")
                        print(f"Trace ID: {result.trace_id}")
                        print(f"{'=' * 60}\n")

                    return 0 if result.execution_status == "success" else 1
                except ImportError:
                    print(
                        "LLM libraries not installed. Install with: pip install hermes-prime[llm]"
                    )
                    return 1
                except Exception as e:
                    print(f"Error executing autonomous task: {e}")
                    if args.json:
                        _emit({"error": str(e)}, True)
                    return 1

            # Phase 8: Graphify commands
            if args.command == "graphify":
                from hermes_prime.memory.graphify_bridge import GraphifyBridge

                bridge = GraphifyBridge(workspace_path=workspace)

                if args.graphify_command == "status":
                    if bridge.available:
                        loaded = bridge.load_existing_graph()
                        nodes = len(bridge.get_nodes()) if loaded else 0
                        edges = len(bridge.get_edges()) if loaded else 0
                        if args.json:
                            _emit(
                                {
                                    "available": True,
                                    "graph_loaded": loaded,
                                    "nodes": nodes,
                                    "edges": edges,
                                },
                                True,
                            )
                        else:
                            print(
                                f"graphify: available, graph loaded={loaded} ({nodes} nodes, {edges} edges)"
                            )
                    else:
                        if args.json:
                            _emit({"available": False}, True)
                        else:
                            print("graphify: not available (install with: pip install graphifyy)")
                    return 0

                elif args.graphify_command == "build":
                    if not bridge.available:
                        print("graphify is not installed. Install with: pip install graphifyy")
                        return 1
                    target = args.target or workspace
                    print(f"Building graphify knowledge graph for {target}...")
                    try:
                        result = bridge.extract(target_path=target)
                        print(
                            f"Graph built: {len(result.get('nodes', []))} nodes, {len(result.get('edges', []))} edges"
                        )
                        return 0
                    except Exception as e:
                        print(f"Error building graph: {e}")
                        return 1

                elif args.graphify_command == "query":
                    loaded = bridge.load_existing_graph()
                    if not loaded:
                        print("No graph found. Run 'hermes-prime graphify build' first.")
                        return 1
                    subgraph = bridge.query_subgraph(args.query, depth=args.depth)
                    nodes = subgraph.get("nodes", [])
                    edges = subgraph.get("edges", [])
                    if args.json:
                        _emit({"query": args.query, "nodes": nodes, "edges": edges}, True)
                    else:
                        print(f"\nGraphify Query: {args.query}")
                        print(f"{'=' * 60}")
                        print(f"Subgraph: {len(nodes)} nodes, {len(edges)} edges")
                        for n in nodes[:20]:
                            label = n.get("label", n.get("name", n.get("id", "?")))
                            print(f"  - {label}")
                        if len(nodes) > 20:
                            print(f"  ... and {len(nodes) - 20} more")
                    return 0

                elif args.graphify_command == "import":
                    from hermes_prime.memory.graph import KnowledgeGraph

                    loaded = bridge.load_existing_graph(graph_path=args.graph_path)
                    if not loaded:
                        print("No graph to import. Build or specify --graph-path.")
                        return 1
                    kg = KnowledgeGraph()
                    count = bridge.import_to_knowledge_graph(kg)
                    print(f"Imported {count} edges into KnowledgeGraph")
                    return 0

                else:
                    parser.error("unknown graphify command")
                return 0

            if args.command == "chat":
                try:
                    from hermes_prime.orch.governed_cli import run_governed_chat
                except ImportError:
                    print("chat requires upstream hermes-agent", file=sys.stderr)
                    return 1
                return run_governed_chat(
                    model=args.model,
                    scope=args.scope,
                    context=args.context,
                )

            if args.command == "gateway":
                try:
                    from hermes_prime.gateway.governed_gateway import run_governed_gateway
                except ImportError:
                    print("gateway requires upstream hermes-agent", file=sys.stderr)
                    return 1
                return run_governed_gateway(
                    platforms=args.platforms.split(","),
                )

            if args.command == "skills":
                from hermes_prime.agent.skills import SkillManager, SkillStore

                skill_store = SkillStore(workspace_path / ".hermes-prime" / "skills.json")
                skill_mgr = SkillManager(skill_store)

                if args.skills_command == "list":
                    results = skill_mgr.skills_list(query=args.query)
                    print(results)
                    return 0
                elif args.skills_command == "view":
                    print(skill_mgr.skill_view(args.name))
                    return 0
                elif args.skills_command == "create":
                    tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
                    result = skill_mgr.skill_manage(
                        action="create", name=args.name, content=args.content,
                        language=args.language, description=args.description, tags=tags,
                    )
                    print(result)
                    return 0
                elif args.skills_command == "delete":
                    print(skill_mgr.skill_manage(action="delete", name=args.name))
                    return 0
                else:
                    parser.error("unknown skills command")
                return 0

            if args.command == "sessions":
                from hermes_prime.agent.session import SessionStore

                session_store = SessionStore(workspace_path / ".hermes-prime" / "sessions.db")

                if args.sessions_command == "list":
                    sessions = session_store.list_sessions()
                    if not sessions:
                        print("No sessions found.")
                    else:
                        for s in sessions:
                            print(f"  {s['id'][:16]}... {s['title']} ({s['message_count']} msgs)")
                    return 0
                elif args.sessions_command == "search":
                    results = session_store.search(args.query)
                    if not results:
                        print(f"No sessions matching '{args.query}'")
                    else:
                        for r in results:
                            print(f"  {r['id'][:16]}... {r['title']} ({r['message_count']} msgs)")
                    return 0
                elif args.sessions_command == "view":
                    msgs = session_store.get_messages(args.session_id)
                    if not msgs:
                        print("No messages in this session.")
                    else:
                        for m in msgs:
                            print(f"[{m['role']}] {m['content'][:200]}")
                    return 0
                else:
                    parser.error("unknown sessions command")
                return 0

            if args.command == "todo":
                from hermes_prime.agent.tools.todo import TodoManager

                todo_mgr = TodoManager()

                if args.todo_command == "create":
                    subtasks = [s.strip() for s in args.subtasks.split(",")] if args.subtasks else []
                    task = todo_mgr.create(args.title, subtasks=subtasks, priority=args.priority)
                    print(f"Task created: {task['id'][:16]}...")
                    return 0
                elif args.todo_command == "list":
                    print(todo_mgr.format_plan())
                    return 0
                elif args.todo_command == "complete":
                    if todo_mgr.complete(args.task_id):
                        print(f"Task {args.task_id[:16]}... completed.")
                    else:
                        print(f"Task {args.task_id[:16]}... not found.")
                    return 0
                elif args.todo_command == "remove":
                    if todo_mgr.remove(args.task_id):
                        print(f"Task {args.task_id[:16]}... removed.")
                    else:
                        print(f"Task {args.task_id[:16]}... not found.")
                    return 0
                else:
                    parser.error("unknown todo command")
                return 0

            if args.command == "tools":
                from hermes_prime.agent.tool_registry import ToolRegistry
                from hermes_prime.agent.tools.web_search import web_search, web_fetch
                from hermes_prime.agent.tools.terminal import terminal_execute
                from hermes_prime.agent.tools.todo import TodoManager

                registry = ToolRegistry()
                registry.register("web_search", web_search, "Search the web")
                registry.register("web_fetch", web_fetch, "Fetch a URL")
                registry.register("terminal", terminal_execute, "Execute shell commands")
                registry.register("todo", TodoManager().format_plan, "Task planning")

                tools = registry.list_tools()
                if args.search:
                    tools = [t for t in tools if args.search.lower() in t.lower()]
                if args.json:
                    _emit({"tools": tools, "count": len(tools)}, True)
                else:
                    print(f"Available tools ({len(tools)}):")
                    for t in sorted(tools):
                        schema = registry.get_schema(t)
                        desc = schema["description"] if schema else ""
                        print(f"  - {t}: {desc[:60]}")
                return 0

            if args.prompt is None:
                parser.error("prompt is required when no subcommand is provided")

            if args.autonomous:
                # Autonomous path with LLM
                try:
                    from hermes_prime.llm.ollama_adapter import OllamaClient
                    from hermes_prime.autonomous.executor import AutonomousExecutor

                    client = OllamaClient()
                    if not client.health_check():
                        print("Ollama is not running. Start it with: ollama serve")
                        return 1

                    executor = AutonomousExecutor(
                        llm_client=client,
                        sentinel=sentinel,
                        vault=vault,
                        trust_store=trust_store,
                        workspace_root=workspace,
                    )
                    result = executor.execute(
                        task_prompt=args.prompt,
                        model=args.model,
                    )

                    if args.json:
                        _emit(
                            {
                                "execution_id": result.execution_id,
                                "status": result.execution_status,
                                "trace_id": result.trace_id,
                            },
                            True,
                        )
                    else:
                        print(f"Autonomous: {result.summary}")
                    return 0
                except ImportError:
                    print(
                        "LLM libraries not installed. Install with: pip install hermes-prime[llm]"
                    )
                    return 1
                except Exception as e:
                    print(f"Error: {e}")
                    return 1
            else:
                # Legacy orchestrator path
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

    return handle_hp_command(args)


if __name__ == "__main__":
    from hermes_prime.recovery import safe_main

    raise SystemExit(safe_main(lambda: main()))
