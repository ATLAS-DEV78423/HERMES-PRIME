"""
File Miner: find files by path, name, or metadata.

Fully deterministic. No LLM involvement.
"""

from __future__ import annotations

import fnmatch
import time
from datetime import datetime, timezone
from pathlib import Path

from refrlow.miners.base import Miner
from refrlow.protocol import (
    DispatchReport,
    DispatchRequest,
    Integrity,
    Status,
    utc_now_iso,
)
from refrlow.sandbox import iter_scoped_files


class FileMiner(Miner):
    class_name = "file_miner"
    tasks = {
        "find_by_glob",
        "find_by_extension",
        "find_recent",
        "find_large",
        "enumerate_tree",
    }

    def execute(self, request: DispatchRequest) -> DispatchReport:
        start_mono, started_at = self._start()
        deadline = start_mono + request.budget.ttl_seconds

        try:
            if request.task == "find_by_glob":
                result, status = self._find_by_glob(request, deadline)
            elif request.task == "find_by_extension":
                result, status = self._find_by_extension(request, deadline)
            elif request.task == "find_recent":
                result, status = self._find_recent(request, deadline)
            elif request.task == "find_large":
                result, status = self._find_large(request, deadline)
            elif request.task == "enumerate_tree":
                result, status = self._enumerate_tree(request, deadline)
            else:
                # Should be unreachable; dispatcher checks tasks.
                return DispatchReport(
                    request_id=request.request_id,
                    subagent=self.class_name,
                    task=request.task,
                    status=Status.ERROR,
                    result={},
                    started_at=started_at,
                    completed_at=utc_now_iso(),
                    elapsed_ms=self._elapsed_ms(start_mono),
                    error_message=f"unknown task: {request.task}",
                )
        except Exception as exc:  # pylint: disable=broad-except
            return DispatchReport(
                request_id=request.request_id,
                subagent=self.class_name,
                task=request.task,
                status=Status.ERROR,
                result={},
                started_at=started_at,
                completed_at=utc_now_iso(),
                elapsed_ms=self._elapsed_ms(start_mono),
                error_message=str(exc),
            )

        return DispatchReport(
            request_id=request.request_id,
            subagent=self.class_name,
            task=request.task,
            status=status,
            result=result,
            started_at=started_at,
            completed_at=utc_now_iso(),
            elapsed_ms=self._elapsed_ms(start_mono),
            tokens_used=0,  # deterministic, no LLM tokens
            scope_searched=request.scope.to_dict(),
            integrity=Integrity(report_hash="sha256:pending"),
        )

    # --- task implementations ---

    def _find_by_glob(
        self, request: DispatchRequest, deadline: float
    ) -> tuple[dict, Status]:
        pattern = request.params.get("pattern", "**/*")
        all_files = iter_scoped_files(request.scope)
        root = Path(request.scope.root).resolve()
        matches = []
        total = 0
        for fp in all_files:
            if time.monotonic() > deadline:
                return (
                    {
                        "matches": matches,
                        "total_matches": total,
                        "returned": len(matches),
                    },
                    Status.TIMEOUT,
                )
            rel = str(fp.relative_to(root))
            if fnmatch.fnmatch(rel, pattern):
                total += 1
                if len(matches) < request.budget.max_results:
                    stat = fp.stat()
                    matches.append(
                        {
                            "path": rel,
                            "size_bytes": stat.st_size,
                            "modified_at": datetime.fromtimestamp(
                                stat.st_mtime, tz=timezone.utc
                            ).isoformat(),
                        }
                    )
        status = (
            Status.OK
            if total == len(matches)
            else Status.TRUNCATED
            if matches
            else Status.NO_RESULTS
        )
        return (
            {
                "matches": matches,
                "total_matches": total,
                "returned": len(matches),
            },
            status,
        )

    def _find_by_extension(
        self, request: DispatchRequest, deadline: float
    ) -> tuple[dict, Status]:
        ext = request.params.get("ext", "")
        if not ext.startswith("."):
            ext = "." + ext
        pattern = f"**/*{ext}"
        # Reuse find_by_glob logic.
        return self._find_by_glob(
            DispatchRequest(
                subagent=request.subagent,
                task="find_by_glob",
                params={"pattern": pattern},
                scope=request.scope,
                budget=request.budget,
                justification=request.justification,
                request_id=request.request_id,
            ),
            deadline,
        )

    def _find_recent(
        self, request: DispatchRequest, deadline: float
    ) -> tuple[dict, Status]:
        since_iso = request.params.get("since")
        if not since_iso:
            raise ValueError("find_recent requires 'since' parameter (ISO 8601)")
        since = datetime.fromisoformat(since_iso).timestamp()
        all_files = iter_scoped_files(request.scope)
        root = Path(request.scope.root).resolve()
        matches = []
        total = 0
        for fp in all_files:
            if time.monotonic() > deadline:
                break
            stat = fp.stat()
            if stat.st_mtime >= since:
                total += 1
                if len(matches) < request.budget.max_results:
                    matches.append(
                        {
                            "path": str(fp.relative_to(root)),
                            "size_bytes": stat.st_size,
                            "modified_at": datetime.fromtimestamp(
                                stat.st_mtime, tz=timezone.utc
                            ).isoformat(),
                        }
                    )
        # Sort newest-first.
        matches.sort(key=lambda m: m["modified_at"], reverse=True)
        status = (
            Status.OK
            if total == len(matches)
            else Status.TRUNCATED
            if matches
            else Status.NO_RESULTS
        )
        return (
            {
                "matches": matches,
                "total_matches": total,
                "returned": len(matches),
            },
            status,
        )

    def _find_large(
        self, request: DispatchRequest, deadline: float
    ) -> tuple[dict, Status]:
        min_bytes = int(request.params.get("min_bytes", 0))
        all_files = iter_scoped_files(request.scope)
        root = Path(request.scope.root).resolve()
        matches = []
        total = 0
        for fp in all_files:
            if time.monotonic() > deadline:
                break
            stat = fp.stat()
            if stat.st_size >= min_bytes:
                total += 1
                if len(matches) < request.budget.max_results:
                    matches.append(
                        {
                            "path": str(fp.relative_to(root)),
                            "size_bytes": stat.st_size,
                        }
                    )
        matches.sort(key=lambda m: m["size_bytes"], reverse=True)
        status = (
            Status.OK
            if total == len(matches)
            else Status.TRUNCATED
            if matches
            else Status.NO_RESULTS
        )
        return (
            {
                "matches": matches,
                "total_matches": total,
                "returned": len(matches),
            },
            status,
        )

    def _enumerate_tree(
        self, request: DispatchRequest, deadline: float
    ) -> tuple[dict, Status]:
        max_depth = int(request.params.get("max_depth", 3))
        root = Path(request.scope.root).resolve()

        tree: dict = {}

        def walk(path: Path, depth: int, container: dict) -> None:
            if depth > max_depth:
                return
            if time.monotonic() > deadline:
                return
            for child in sorted(path.iterdir()):
                try:
                    if child.is_dir():
                        container[child.name + "/"] = {}
                        walk(child, depth + 1, container[child.name + "/"])
                    else:
                        container[child.name] = None
                except PermissionError:
                    continue

        walk(root, 0, tree)
        return ({"tree": tree, "root": str(root)}, Status.OK)
