from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SkillsManager:
    """Governed skills management wrapping upstream skills hub."""

    def __init__(self, workspace_root: str | Path, sentinel: Any = None, trust_store: Any = None):
        self.workspace_root = Path(workspace_root).resolve()
        self.sentinel = sentinel
        self.trust_store = trust_store

    def _audit(self, action: str, detail: dict[str, Any]) -> None:
        if not self.trust_store:
            return
        from hermes_prime.contracts import AuditTrace
        from hermes_prime.utils import new_urn_uuid, utc_now_iso
        trace = AuditTrace(
            trace_id=new_urn_uuid(),
            trace_type="skills",
            created_at=utc_now_iso(),
            workspace_root=str(self.workspace_root),
            action={"type": action, **detail},
            decision={"permitted": True},
            mutation=detail,
            summary=f"Skills: {action}",
        )
        self.trust_store.store_audit_trace(trace)

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        try:
            from tools.skills_hub import unified_search
            results = unified_search(query, sources="all", source_filter="all", limit=limit)
            return [
                {
                    "name": r.name,
                    "identifier": r.identifier,
                    "description": r.description,
                    "source": r.source,
                    "trust_level": r.trust_level,
                    "version": getattr(r, "version", ""),
                }
                for r in results
            ]
        except ImportError:
            return [{"error": "Upstream skills hub not available"}]

    def browse(self, page: int = 1, source: str = "all") -> list[dict[str, Any]]:
        try:
            from tools.skills_hub import fetch_skill_index
            index = fetch_skill_index(source_filter=source)
            items = list(index.values()) if isinstance(index, dict) else index
            per_page = 20
            start = (page - 1) * per_page
            return [
                {
                    "name": getattr(s, "name", str(s)),
                    "identifier": getattr(s, "identifier", ""),
                    "description": getattr(s, "description", ""),
                    "source": getattr(s, "source", source),
                }
                for s in items[start:start + per_page]
            ]
        except ImportError:
            return [{"error": "Upstream skills hub not available"}]

    def inspect(self, identifier: str) -> dict[str, Any]:
        try:
            from tools.skills_hub import fetch_skill_detail
            detail = fetch_skill_detail(identifier)
            if hasattr(detail, "to_dict"):
                return detail.to_dict()
            if isinstance(detail, dict):
                return detail
            return {"content": str(detail)}
        except ImportError:
            return {"error": "Upstream skills hub not available"}

    def install(self, identifier: str) -> dict[str, Any]:
        try:
            from tools.skills_hub import do_install_skill
            result = do_install_skill(identifier)
            self._audit("install", {"identifier": identifier, "result": str(result)})
            if isinstance(result, dict):
                return result
            return {"status": "installed", "identifier": identifier, "detail": str(result)}
        except ImportError:
            return {"error": "Upstream skills hub not available"}
        except Exception as e:
            return {"error": str(e)}

    def list_installed(self, source: str = "all") -> list[dict[str, Any]]:
        try:
            from agent.skill_utils import discover_skills
            skills = discover_skills(source_filter=source)
            return [
                {
                    "name": s.name if hasattr(s, "name") else str(s),
                    "description": s.description if hasattr(s, "description") else "",
                    "source": s.source if hasattr(s, "source") else "local",
                    "version": s.version if hasattr(s, "version") else "",
                }
                for s in skills
            ]
        except ImportError:
            return [{"error": "Upstream skill discovery not available"}]

    def uninstall(self, name: str) -> dict[str, Any]:
        try:
            from tools.skills_hub import do_remove_skill
            result = do_remove_skill(name)
            self._audit("uninstall", {"name": name, "result": str(result)})
            return {"status": "uninstalled", "name": name}
        except ImportError:
            return {"error": "Upstream skills hub not available"}
        except Exception as e:
            return {"error": str(e)}

    def check_updates(self) -> list[dict[str, Any]]:
        try:
            from tools.skills_hub import check_skill_updates
            results = check_skill_updates()
            return [
                {"name": r.name if hasattr(r, "name") else str(r), "update_available": True}
                for r in results
            ]
        except ImportError:
            return [{"error": "Upstream skills hub not available"}]
