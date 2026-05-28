from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class CronManager:
    """Governed cron job management wrapping upstream cron system."""

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
            trace_type="cron",
            created_at=utc_now_iso(),
            workspace_root=str(self.workspace_root),
            action={"type": action, **detail},
            decision={"permitted": True},
            mutation=detail,
            summary=f"Cron: {action}",
        )
        self.trust_store.store_audit_trace(trace)

    def list_jobs(self, include_disabled: bool = False) -> list[dict[str, Any]]:
        try:
            from cron.jobs import list_jobs
            jobs = list_jobs(include_disabled=include_disabled)
            return [
                {
                    "id": j.get("id", ""),
                    "name": j.get("name", "(unnamed)"),
                    "schedule": j.get("schedule", {}),
                    "schedule_display": j.get("schedule_display", ""),
                    "state": j.get("state", "scheduled" if j.get("enabled", True) else "paused"),
                    "enabled": j.get("enabled", True),
                    "skill": j.get("skill", ""),
                    "skills": j.get("skills", []),
                    "model": j.get("model"),
                    "provider": j.get("provider"),
                    "workdir": j.get("workdir"),
                    "next_run_at": j.get("next_run_at", ""),
                    "last_run_at": j.get("last_run_at", ""),
                    "last_result": j.get("last_result"),
                }
                for j in jobs
            ]
        except ImportError:
            return [{"error": "Upstream cron not available"}]

    def create_job(
        self,
        name: str,
        schedule: str,
        prompt: str,
        model: str | None = None,
        provider: str | None = None,
        skills: list[str] | None = None,
        workdir: str | None = None,
        deliver: list[str] | None = None,
    ) -> dict[str, Any]:
        try:
            from cron.jobs import add_job
            job_id = add_job(
                name=name,
                schedule=schedule,
                prompt=prompt,
                model=model,
                provider=provider,
                skills=skills,
                workdir=workdir,
                deliver=deliver or ["local"],
            )
            self._audit("create", {"job_id": job_id, "name": name, "schedule": schedule})
            return {"id": job_id, "name": name, "status": "created"}
        except ImportError:
            return {"error": "Upstream cron not available"}
        except Exception as e:
            return {"error": str(e)}

    def edit_job(self, job_id: str, **updates: Any) -> dict[str, Any]:
        try:
            from cron.jobs import update_job
            update_job(job_id, **updates)
            self._audit("edit", {"job_id": job_id, **updates})
            return {"id": job_id, "status": "updated"}
        except ImportError:
            return {"error": "Upstream cron not available"}
        except Exception as e:
            return {"error": str(e)}

    def pause_job(self, job_id: str) -> dict[str, Any]:
        try:
            from cron.jobs import pause_job
            pause_job(job_id)
            self._audit("pause", {"job_id": job_id})
            return {"id": job_id, "status": "paused"}
        except ImportError:
            return {"error": "Upstream cron not available"}

    def resume_job(self, job_id: str) -> dict[str, Any]:
        try:
            from cron.jobs import resume_job
            resume_job(job_id)
            self._audit("resume", {"job_id": job_id})
            return {"id": job_id, "status": "resumed"}
        except ImportError:
            return {"error": "Upstream cron not available"}

    def run_job(self, job_id: str) -> dict[str, Any]:
        try:
            from cron.jobs import trigger_job
            trigger_job(job_id)
            self._audit("run", {"job_id": job_id})
            return {"id": job_id, "status": "triggered"}
        except ImportError:
            return {"error": "Upstream cron not available"}

    def remove_job(self, job_id: str) -> dict[str, Any]:
        try:
            from cron.jobs import remove_job
            remove_job(job_id)
            self._audit("remove", {"job_id": job_id})
            return {"id": job_id, "status": "removed"}
        except ImportError:
            return {"error": "Upstream cron not available"}

    def scheduler_status(self) -> dict[str, Any]:
        try:
            from cron.scheduler import scheduler_status
            return scheduler_status()
        except ImportError:
            return {"status": "upstream cron not available"}

    def tick(self) -> dict[str, Any]:
        try:
            from cron.scheduler import tick
            result = tick()
            return {"status": "tick completed", "result": str(result)}
        except ImportError:
            return {"error": "Upstream cron not available"}
