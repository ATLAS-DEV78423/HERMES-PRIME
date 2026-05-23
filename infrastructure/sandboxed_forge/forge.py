from __future__ import annotations

import difflib
import hashlib
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from hermes_prime.contracts import ActionProposal, ActionType, RiskTier, SentinelDecision
from hermes_prime.utils import canonical_json, hash_struct, new_urn_uuid, utc_now_iso


@dataclass
class JournalEntry:
    index: int
    timestamp: str
    operation: str
    path: str
    before_hash: str | None
    after_hash: str | None
    payload: dict[str, Any]
    previous_hash: str
    entry_hash: str


class ForgeJournal:
    def __init__(self) -> None:
        self.entries: list[JournalEntry] = []
        self.head_hash = "sha256:" + "0" * 64

    def append(
        self,
        operation: str,
        path: str,
        before_hash: str | None,
        after_hash: str | None,
        payload: dict[str, Any] | None = None,
    ) -> JournalEntry:
        payload = payload or {}
        timestamp = utc_now_iso()
        entry_payload = {
            "index": len(self.entries),
            "timestamp": timestamp,
            "operation": operation,
            "path": path,
            "before_hash": before_hash,
            "after_hash": after_hash,
            "payload": payload,
            "previous_hash": self.head_hash,
        }
        entry_hash = "sha256:" + hashlib.sha256(
            canonical_json(entry_payload).encode("utf-8")
        ).hexdigest()
        entry = JournalEntry(
            index=len(self.entries),
            timestamp=timestamp,
            operation=operation,
            path=path,
            before_hash=before_hash,
            after_hash=after_hash,
            payload=payload,
            previous_hash=self.head_hash,
            entry_hash=entry_hash,
        )
        self.entries.append(entry)
        self.head_hash = entry_hash
        return entry


@dataclass
class ForgeSession:
    workspace_root: Path
    overlay_root: Path
    intent_root: str
    capability: str
    authorizer: Callable[[ActionProposal], SentinelDecision] | None
    journal: ForgeJournal = field(default_factory=ForgeJournal)
    snapshots: dict[str, str] = field(default_factory=dict)

    def _resolve(self, relative_path: str) -> Path:
        target = (self.workspace_root / relative_path).resolve()
        try:
            target.relative_to(self.workspace_root.resolve())
        except ValueError as exc:
            raise ValueError("path outside workspace root") from exc
        return target

    def _overlay_path(self, target: Path) -> Path:
        rel = target.relative_to(self.workspace_root.resolve())
        return self.overlay_root / rel

    def _load_current(self, target: Path) -> str:
        overlay = self._overlay_path(target)
        if overlay.exists():
            return overlay.read_text(encoding="utf-8")
        if target.exists():
            return target.read_text(encoding="utf-8")
        return ""

    def _load_base(self, target: Path) -> str:
        if target.exists():
            return target.read_text(encoding="utf-8")
        return ""

    def _authorize(
        self,
        action_type: ActionType,
        target: Path,
        risk_tier: RiskTier,
        parameters: dict[str, Any],
    ) -> SentinelDecision:
        if self.authorizer is None:
            raise PermissionError("mutation requires Sentinel authorization")
        decision = self.authorizer(
            ActionProposal(
                action_id=new_urn_uuid(),
                action_type=action_type,
                scope=str(target),
                risk_tier=risk_tier,
                intent_root=self.intent_root,
                capability=self.capability,
                proposed_at=utc_now_iso(),
                parameters=parameters,
            )
        )
        if not decision.permitted:
            layer = f"layer_{decision.blocking_layer}" if decision.blocking_layer is not None else "layer_unknown"
            reason = decision.denial_reason or "sentinel_denied"
            raise PermissionError(f"sentinel_denied:{layer}:{reason}")
        return decision

    def read_text(self, relative_path: str) -> str:
        target = self._resolve(relative_path)
        return self._load_current(target)

    def write_text(self, relative_path: str, content: str) -> None:
        target = self._resolve(relative_path)
        decision = self._authorize(
            ActionType.FILESYSTEM_WRITE,
            target,
            RiskTier.T1,
            {"bytes": len(content.encode("utf-8"))},
        )
        before = self._load_current(target)
        before_hash = hash_struct(before) if before else None
        overlay = self._overlay_path(target)
        overlay.parent.mkdir(parents=True, exist_ok=True)
        overlay.write_text(content, encoding="utf-8")
        after_hash = hash_struct(content)
        if relative_path not in self.snapshots and target.exists():
            self.snapshots[relative_path] = hash_struct(before)
        self.journal.append(
            "write",
            str(target),
            before_hash=before_hash,
            after_hash=after_hash,
            payload={"bytes": len(content.encode("utf-8")), "decision": decision.to_dict()},
        )

    def delete(self, relative_path: str) -> None:
        target = self._resolve(relative_path)
        decision = self._authorize(
            ActionType.FILESYSTEM_WRITE,
            target,
            RiskTier.T1,
            {"delete": True},
        )
        before = self._load_current(target)
        before_hash = hash_struct(before) if before else None
        overlay = self._overlay_path(target)
        overlay.parent.mkdir(parents=True, exist_ok=True)
        tombstone = overlay.with_suffix(overlay.suffix + ".deleted")
        tombstone.write_text("deleted", encoding="utf-8")
        if relative_path not in self.snapshots and target.exists():
            self.snapshots[relative_path] = hash_struct(before)
        self.journal.append(
            "delete",
            str(target),
            before_hash=before_hash,
            after_hash=None,
            payload={"decision": decision.to_dict()},
        )

    def diff(self, relative_path: str) -> str:
        target = self._resolve(relative_path)
        before = self._load_base(target)
        overlay = self._overlay_path(target)
        after = ""
        if overlay.exists():
            after = overlay.read_text(encoding="utf-8")
        elif overlay.with_suffix(overlay.suffix + ".deleted").exists():
            after = ""
        return "".join(
            difflib.unified_diff(
                before.splitlines(True),
                after.splitlines(True),
                fromfile=f"a/{relative_path}",
                tofile=f"b/{relative_path}",
            )
        )

    def list_changes(self) -> list[str]:
        changes: list[str] = []
        for path in self.overlay_root.rglob("*"):
            if path.is_file() and not path.name.endswith(".deleted"):
                changes.append(path.relative_to(self.overlay_root).as_posix())
        return sorted(changes)

    def rollback(self) -> None:
        if self.overlay_root.exists():
            shutil.rmtree(self.overlay_root)
        self.overlay_root.mkdir(parents=True, exist_ok=True)
        self.snapshots.clear()
        self.journal.append("rollback", str(self.workspace_root), None, None, {})

    def commit(self) -> list[str]:
        committed_candidates = self.list_changes()
        commit_target = self.workspace_root
        decision = self._authorize(
            ActionType.FILESYSTEM_COMMIT,
            commit_target,
            RiskTier.T2,
            {"files": committed_candidates},
        )
        committed: list[str] = []
        for staged in committed_candidates:
            source = self.overlay_root / staged
            target = self.workspace_root / staged
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            committed.append(staged)
        for deleted_marker in self.overlay_root.rglob("*.deleted"):
            relative = deleted_marker.relative_to(self.overlay_root)
            original = self.workspace_root / relative.as_posix().removesuffix(".deleted")
            if original.exists():
                original.unlink()
                committed.append(original.relative_to(self.workspace_root).as_posix())
        self.journal.append(
            "commit",
            str(self.workspace_root),
            None,
            None,
            {"files": committed, "decision": decision.to_dict()},
        )
        return committed


class SandboxedForge:
    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.overlay_root = Path(tempfile.mkdtemp(prefix="hermes-forge-overlay-"))

    def start_session(
        self,
        intent_root: str,
        capability: str,
        authorizer: Callable[[ActionProposal], SentinelDecision] | None,
    ) -> ForgeSession:
        self.overlay_root.mkdir(parents=True, exist_ok=True)
        return ForgeSession(
            workspace_root=self.workspace_root,
            overlay_root=self.overlay_root,
            intent_root=intent_root,
            capability=capability,
            authorizer=authorizer,
        )
