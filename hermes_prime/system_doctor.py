"""Hermes Prime system diagnostics and self-repair."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import shutil
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from infrastructure.backends import BackendRegistry
from infrastructure.policy_engine.bundle import PolicyBundle
from infrastructure.trust_store import TrustStore
from hermes_prime.memory.backends.sqlite_backend import SQLiteMemoryBackend


class Severity(str, Enum):
    OK = "ok"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class CheckResult:
    check_id: str
    category: str
    severity: Severity
    message: str
    auto_fixable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "category": self.category,
            "severity": self.severity.value,
            "message": self.message,
            "auto_fixable": self.auto_fixable,
            "details": dict(self.details),
        }


@dataclass
class RepairAction:
    action_id: str
    description: str
    applied: bool
    success: bool
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "description": self.description,
            "applied": self.applied,
            "success": self.success,
            "message": self.message,
        }


@dataclass
class DoctorReport:
    workspace_root: str
    hermes_version: str
    python_version: str
    checks: list[CheckResult] = field(default_factory=list)
    readiness: dict[str, Any] = field(default_factory=dict)
    vault: dict[str, Any] = field(default_factory=dict)

    @property
    def healthy(self) -> bool:
        return not any(c.severity == Severity.ERROR for c in self.checks)

    @property
    def fixable_count(self) -> int:
        return sum(1 for c in self.checks if c.auto_fixable and c.severity != Severity.OK)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_root": self.workspace_root,
            "hermes_version": self.hermes_version,
            "python_version": self.python_version,
            "healthy": self.healthy,
            "fixable_count": self.fixable_count,
            "checks": [c.to_dict() for c in self.checks],
            "readiness": self.readiness,
            "vault": self.vault,
        }


@dataclass
class RepairReport:
    workspace_root: str
    dry_run: bool
    actions: list[RepairAction] = field(default_factory=list)

    @property
    def repaired(self) -> bool:
        return any(a.applied and a.success for a in self.actions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_root": self.workspace_root,
            "dry_run": self.dry_run,
            "repaired": self.repaired,
            "actions": [a.to_dict() for a in self.actions],
        }


def _package_version() -> str:
    try:
        return importlib.metadata.version("hermes-prime")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


def _sqlite_integrity(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return True, "missing"
    try:
        conn = sqlite3.connect(str(path), timeout=5)
        row = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        result = row[0] if row else "unknown"
        return result == "ok", result
    except sqlite3.Error as exc:
        return False, str(exc)


def _module_ok(name: str) -> bool:
    if importlib.util.find_spec(name) is None:
        return False
    try:
        importlib.import_module(name)
        return True
    except Exception:
        return False


def run_doctor(workspace_root: str | Path) -> DoctorReport:
    """Run full system diagnostics for a Hermes Prime workspace."""
    root = Path(workspace_root).resolve()
    hermes_dir = root / ".hermes-prime"
    policy_root = root / "infrastructure" / "policy_engine"
    trust_path = hermes_dir / "trust.db"
    memory_path = hermes_dir / "memory.db"
    fabric_root = root / "external" / "fabric"

    report = DoctorReport(
        workspace_root=str(root),
        hermes_version=_package_version(),
        python_version=(
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        ),
    )

    def add(check: CheckResult) -> None:
        report.checks.append(check)

    # --- Workspace layout ---
    if not hermes_dir.exists():
        add(
            CheckResult(
                "layout.hermes_dir",
                "layout",
                Severity.ERROR,
                f"Missing state directory: {hermes_dir}",
                auto_fixable=True,
            )
        )
    else:
        add(
            CheckResult(
                "layout.hermes_dir",
                "layout",
                Severity.OK,
                f"State directory present: {hermes_dir}",
            )
        )

    for sub in ("bin", "palace"):
        sub_path = hermes_dir / sub
        if hermes_dir.exists() and not sub_path.exists():
            add(
                CheckResult(
                    f"layout.{sub}",
                    "layout",
                    Severity.WARNING,
                    f"Missing subdirectory: {sub_path}",
                    auto_fixable=True,
                )
            )

    # --- Policy bundle ---
    if not policy_root.exists():
        add(
            CheckResult(
                "policy.root",
                "policy",
                Severity.ERROR,
                f"Policy engine root not found: {policy_root}",
                auto_fixable=False,
            )
        )
    else:
        policies = policy_root / "policies"
        schemas = policy_root / "schemas"
        if not policies.is_dir():
            add(
                CheckResult(
                    "policy.policies",
                    "policy",
                    Severity.ERROR,
                    f"Missing policies directory: {policies}",
                    auto_fixable=True,
                )
            )
        if not schemas.is_dir():
            add(
                CheckResult(
                    "policy.schemas",
                    "policy",
                    Severity.ERROR,
                    f"Missing schemas directory: {schemas}",
                    auto_fixable=True,
                )
            )
        bundle = PolicyBundle(policy_root)
        report.readiness = bundle.readiness()
        if bundle.available():
            add(
                CheckResult(
                    "policy.bundle",
                    "policy",
                    Severity.OK,
                    "Policy bundle is available",
                )
            )
        else:
            add(
                CheckResult(
                    "policy.bundle",
                    "policy",
                    Severity.ERROR,
                    "Policy bundle is not available (missing artifacts)",
                    auto_fixable=False,
                    details=bundle.manifest(),
                )
            )

    # --- Infrastructure backends ---
    registry = BackendRegistry(root)
    backend_readiness = registry.readiness()
    if backend_readiness.get("ready"):
        add(
            CheckResult(
                "backends.ready",
                "backends",
                Severity.OK,
                "Critical backends ready (OPA + tree-sitter)",
            )
        )
    else:
        missing = backend_readiness.get("critical_missing", [])
        add(
            CheckResult(
                "backends.ready",
                "backends",
                Severity.ERROR,
                f"Missing critical backends: {', '.join(missing) or 'unknown'}",
                auto_fixable=False,
                details=registry.manifest(),
            )
        )

    # --- Python runtime dependencies ---
    for mod, label in (
        ("pydantic", "pydantic"),
        ("tree_sitter", "tree-sitter"),
        ("wasmtime", "wasmtime"),
        ("requests", "requests"),
    ):
        if _module_ok(mod):
            add(
                CheckResult(
                    f"deps.{mod}",
                    "dependencies",
                    Severity.OK,
                    f"{label} is importable",
                )
            )
        else:
            add(
                CheckResult(
                    f"deps.{mod}",
                    "dependencies",
                    Severity.ERROR,
                    f"{label} is not installed (pip install hermes-prime)",
                    auto_fixable=False,
                    details={"hint": f"pip install {label}"},
                )
            )

    for mod, label, extra in (
        ("chromadb", "chromadb", "memory backends (mem0/atlas)"),
        ("mempalace", "mempalace", "MemPalace backend"),
        ("graphify", "graphify", "Graphify integration"),
        ("ollama", "ollama", "local LLM (Ollama)"),
        ("hvac", "hvac", "HashiCorp Vault client"),
    ):
        if _module_ok(mod):
            add(
                CheckResult(
                    f"deps.optional.{mod}",
                    "dependencies",
                    Severity.OK,
                    f"Optional: {label} available ({extra})",
                )
            )
        else:
            add(
                CheckResult(
                    f"deps.optional.{mod}",
                    "dependencies",
                    Severity.INFO,
                    f"Optional: {label} not installed ({extra})",
                    auto_fixable=False,
                )
            )

    # --- Trust store database ---
    trust_ok, trust_detail = _sqlite_integrity(trust_path)
    if not trust_path.exists():
        add(
            CheckResult(
                "storage.trust",
                "storage",
                Severity.WARNING,
                "Trust store database does not exist yet",
                auto_fixable=True,
            )
        )
    elif trust_ok:
        add(
            CheckResult(
                "storage.trust",
                "storage",
                Severity.OK,
                f"Trust store OK: {trust_path}",
            )
        )
    else:
        add(
            CheckResult(
                "storage.trust",
                "storage",
                Severity.ERROR,
                f"Trust store integrity failed: {trust_detail}",
                auto_fixable=True,
                details={"path": str(trust_path)},
            )
        )

    # --- Memory database ---
    mem_ok, mem_detail = _sqlite_integrity(memory_path)
    if not memory_path.exists():
        add(
            CheckResult(
                "storage.memory",
                "storage",
                Severity.WARNING,
                "Memory database does not exist yet",
                auto_fixable=True,
            )
        )
    elif mem_ok:
        add(
            CheckResult(
                "storage.memory",
                "storage",
                Severity.OK,
                f"Memory store OK: {memory_path}",
            )
        )
    else:
        add(
            CheckResult(
                "storage.memory",
                "storage",
                Severity.ERROR,
                f"Memory database integrity failed: {mem_detail}",
                auto_fixable=True,
                details={"path": str(memory_path)},
            )
        )

    # --- Fabric patterns (optional) ---
    if not fabric_root.exists():
        add(
            CheckResult(
                "fabric.root",
                "fabric",
                Severity.WARNING,
                f"Fabric pattern root not found: {fabric_root}",
                auto_fixable=False,
            )
        )

    # --- Vault health ---
    try:
        from hermes_prime.vault.vault_client import VaultClient

        report.vault = VaultClient(fallback_env_prefix="HERMES_").health()
        if report.vault.get("available"):
            add(
                CheckResult(
                    "vault.health",
                    "vault",
                    Severity.OK,
                    "Vault client available",
                    details=report.vault,
                )
            )
        else:
            add(
                CheckResult(
                    "vault.health",
                    "vault",
                    Severity.INFO,
                    "Vault not configured (env-var fallback only)",
                    details=report.vault,
                )
            )
    except Exception as exc:
        report.vault = {"available": False, "error": str(exc)}
        add(
            CheckResult(
                "vault.health",
                "vault",
                Severity.INFO,
                f"Vault check skipped: {exc}",
            )
        )

    return report


def _backup_file(path: Path) -> Path | None:
    if not path.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_suffix(path.suffix + f".bak.{stamp}")
    shutil.copy2(path, backup)
    return backup


def run_repair(
    workspace_root: str | Path,
    *,
    dry_run: bool = False,
    force_db_reset: bool = False,
) -> RepairReport:
    """Apply safe automatic repairs for issues detected by run_doctor."""
    root = Path(workspace_root).resolve()
    hermes_dir = root / ".hermes-prime"
    policy_root = root / "infrastructure" / "policy_engine"
    trust_path = hermes_dir / "trust.db"
    memory_path = hermes_dir / "memory.db"

    report = RepairReport(workspace_root=str(root), dry_run=dry_run)
    diagnosis = run_doctor(root)

    def record(
        action_id: str,
        description: str,
        applied: bool,
        success: bool,
        message: str = "",
    ) -> None:
        report.actions.append(
            RepairAction(
                action_id=action_id,
                description=description,
                applied=applied,
                success=success,
                message=message,
            )
        )

    fixable = {
        c.check_id
        for c in diagnosis.checks
        if c.auto_fixable and c.severity in (Severity.ERROR, Severity.WARNING)
    }

    # Create .hermes-prime layout
    if "layout.hermes_dir" in fixable or not hermes_dir.exists():
        desc = f"Create state directory {hermes_dir}"
        if dry_run:
            record("layout.hermes_dir", desc, False, True, "would create")
        else:
            hermes_dir.mkdir(parents=True, exist_ok=True)
            record("layout.hermes_dir", desc, True, hermes_dir.is_dir())

    for sub in ("bin", "palace"):
        check_id = f"layout.{sub}"
        sub_path = hermes_dir / sub
        if check_id in fixable or (hermes_dir.exists() and not sub_path.exists()):
            desc = f"Create subdirectory {sub_path}"
            if dry_run:
                record(check_id, desc, False, True, "would create")
            else:
                sub_path.mkdir(parents=True, exist_ok=True)
                record(check_id, desc, True, sub_path.is_dir())

    # Policy scaffolding (only empty dirs — never overwrite rego)
    if policy_root.exists():
        for name, check_id in (("policies", "policy.policies"), ("schemas", "policy.schemas")):
            target = policy_root / name
            if check_id in fixable and not target.is_dir():
                desc = f"Create policy {name} directory"
                if dry_run:
                    record(check_id, desc, False, True, "would create")
                else:
                    target.mkdir(parents=True, exist_ok=True)
                    record(check_id, desc, True, target.is_dir())

    # Trust store
    trust_needs_fix = "storage.trust" in fixable
    trust_ok, _ = _sqlite_integrity(trust_path)
    if trust_needs_fix or (force_db_reset and trust_path.exists() and not trust_ok):
        desc = "Initialize or rebuild trust store database"
        if dry_run:
            record("storage.trust", desc, False, True, "would initialize trust.db")
        else:
            try:
                if trust_path.exists() and not trust_ok:
                    backup = _backup_file(trust_path)
                    trust_path.unlink(missing_ok=True)
                    for suffix in ("-wal", "-shm"):
                        trust_path.with_name(trust_path.name + suffix).unlink(
                            missing_ok=True
                        )
                    msg = f"rebuilt (backup: {backup})" if backup else "rebuilt"
                else:
                    msg = "initialized"
                store = TrustStore(trust_path)
                store.close()
                record("storage.trust", desc, True, True, msg)
            except Exception as exc:
                record("storage.trust", desc, True, False, str(exc))

    # Memory store
    mem_needs_fix = "storage.memory" in fixable
    mem_ok, _ = _sqlite_integrity(memory_path)
    if mem_needs_fix or (force_db_reset and memory_path.exists() and not mem_ok):
        desc = "Initialize or rebuild memory database"
        if dry_run:
            record("storage.memory", desc, False, True, "would initialize memory.db")
        else:
            try:
                if memory_path.exists() and not mem_ok:
                    backup = _backup_file(memory_path)
                    memory_path.unlink(missing_ok=True)
                    for suffix in ("-wal", "-shm"):
                        memory_path.with_name(memory_path.name + suffix).unlink(
                            missing_ok=True
                        )
                    msg = f"rebuilt (backup: {backup})" if backup else "rebuilt"
                else:
                    msg = "initialized"
                backend = SQLiteMemoryBackend(memory_path)
                backend.conn.close()
                record("storage.memory", desc, True, True, msg)
            except Exception as exc:
                record("storage.memory", desc, True, False, str(exc))

    # WAL checkpoint for healthy databases
    if not dry_run:
        for db_path in (trust_path, memory_path):
            if db_path.exists():
                try:
                    conn = sqlite3.connect(str(db_path), timeout=5)
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    conn.close()
                except sqlite3.Error:
                    pass

    return report


def format_doctor_text(report: DoctorReport) -> str:
    lines = [
        f"Hermes Prime v{report.hermes_version} — "
        f"{'healthy' if report.healthy else 'issues detected'}",
        f"  Python: {report.python_version}",
        f"  Workspace: {report.workspace_root}",
    ]
    if report.fixable_count:
        lines.append(f"  Auto-fixable issues: {report.fixable_count} (run: hermes repair)")

    by_severity = {Severity.ERROR: [], Severity.WARNING: [], Severity.INFO: [], Severity.OK: []}
    for check in report.checks:
        if check.severity == Severity.OK:
            continue
        by_severity[check.severity].append(check)

    for severity in (Severity.ERROR, Severity.WARNING, Severity.INFO):
        items = by_severity[severity]
        if not items:
            continue
        lines.append(f"\n{severity.value.upper()}:")
        for item in items:
            fix_hint = " [fixable]" if item.auto_fixable else ""
            lines.append(f"  - [{item.category}] {item.message}{fix_hint}")

    ok_count = sum(1 for c in report.checks if c.severity == Severity.OK)
    lines.append(f"\n{ok_count} checks passed.")
    return "\n".join(lines)


def format_repair_text(report: RepairReport) -> str:
    mode = "dry-run" if report.dry_run else "applied"
    lines = [f"Hermes repair ({mode}) — workspace: {report.workspace_root}"]
    if not report.actions:
        lines.append("  No repairs were necessary.")
        return "\n".join(lines)
    for action in report.actions:
        status = "ok" if action.success else "failed"
        applied = "would apply" if report.dry_run and not action.applied else (
            "applied" if action.applied else "skipped"
        )
        msg = f" — {action.message}" if action.message else ""
        lines.append(f"  [{status}] {action.description} ({applied}){msg}")
    return "\n".join(lines)
