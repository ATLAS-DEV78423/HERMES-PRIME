"""
Grep Miner: search file contents for text or patterns.

Deterministic. Wraps ripgrep if available; falls back to pure-Python.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

from refrlow.miners.base import Miner
from refrlow.protocol import (
    DispatchReport,
    DispatchRequest,
    Integrity,
    Status,
    file_content_hash,
    utc_now_iso,
)
from refrlow.sandbox import iter_scoped_files


# Per T-R10: defend against regex DoS by capping pattern complexity.
MAX_PATTERN_LEN = 256


class GrepMiner(Miner):
    class_name = "grep_miner"
    tasks = {"search_text", "search_word", "count_matches", "find_imports_of"}

    def execute(self, request: DispatchRequest) -> DispatchReport:
        start_mono, started_at = self._start()
        deadline = start_mono + request.budget.ttl_seconds

        try:
            if request.task == "search_text":
                result, status, hashes = self._search_text(request, deadline)
            elif request.task == "search_word":
                params = dict(request.params)
                word = params.get("word", "")
                params["pattern"] = rf"\b{re.escape(word)}\b"
                params["regex"] = True
                request2 = DispatchRequest(
                    subagent=request.subagent,
                    task="search_text",
                    params=params,
                    scope=request.scope,
                    budget=request.budget,
                    justification=request.justification,
                    request_id=request.request_id,
                )
                result, status, hashes = self._search_text(request2, deadline)
            elif request.task == "count_matches":
                result, status, hashes = self._count_matches(request, deadline)
            elif request.task == "find_imports_of":
                module = request.params.get("module", "")
                # Heuristic patterns covering common languages.
                patterns = [
                    rf"import\s+.*{re.escape(module)}",
                    rf"from\s+['\"]?{re.escape(module)}",
                    rf"require\s*\(\s*['\"]{re.escape(module)}",
                ]
                combined = "|".join(patterns)
                params = {"pattern": combined, "regex": True, "context_lines": 1}
                request2 = DispatchRequest(
                    subagent=request.subagent,
                    task="search_text",
                    params=params,
                    scope=request.scope,
                    budget=request.budget,
                    justification=request.justification,
                    request_id=request.request_id,
                )
                result, status, hashes = self._search_text(request2, deadline)
            else:
                return self._error_report(request, started_at, start_mono,
                                          f"unknown task: {request.task}")
        except Exception as exc:  # pylint: disable=broad-except
            return self._error_report(request, started_at, start_mono, str(exc))

        return DispatchReport(
            request_id=request.request_id,
            subagent=self.class_name,
            task=request.task,
            status=status,
            result=result,
            started_at=started_at,
            completed_at=utc_now_iso(),
            elapsed_ms=self._elapsed_ms(start_mono),
            tokens_used=0,
            scope_searched=request.scope.to_dict(),
            integrity=Integrity(
                report_hash="sha256:pending", content_hashes=hashes
            ),
        )

    def _search_text(
        self, request: DispatchRequest, deadline: float
    ) -> tuple[dict, Status, dict[str, str]]:
        pattern = request.params.get("pattern", "")
        if len(pattern) > MAX_PATTERN_LEN:
            raise ValueError(
                f"pattern too long ({len(pattern)} > {MAX_PATTERN_LEN}); "
                f"reject for ReDoS safety"
            )
        is_regex = bool(request.params.get("regex", False))
        ctx_lines = int(request.params.get("context_lines", 0))

        # Prefer ripgrep if available — much faster.
        rg = shutil.which("rg")
        if rg:
            return self._search_with_ripgrep(rg, request, pattern, is_regex, ctx_lines, deadline)
        return self._search_with_python(request, pattern, is_regex, ctx_lines, deadline)

    def _search_with_ripgrep(
        self,
        rg: str,
        request: DispatchRequest,
        pattern: str,
        is_regex: bool,
        ctx_lines: int,
        deadline: float,
    ) -> tuple[dict, Status, dict[str, str]]:
        cmd = [rg, "--json", "--max-count", str(request.budget.max_results)]
        if not is_regex:
            cmd.append("--fixed-strings")
        if ctx_lines:
            cmd.extend(["-C", str(ctx_lines)])
        # Apply exclude globs.
        for glob in request.scope.exclude_globs:
            cmd.extend(["-g", f"!{glob}"])
        cmd.extend([pattern, request.scope.root])

        try:
            timeout = max(1, int(deadline - time.monotonic()))
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired:
            return ({"matches": [], "total_matches": 0, "returned": 0,
                     "note": "ripgrep timeout"}, Status.TIMEOUT, {})

        matches = []
        files_seen: set[str] = set()
        hashes: dict[str, str] = {}
        import json as json_mod
        for line in proc.stdout.splitlines():
            if len(matches) >= request.budget.max_results:
                break
            try:
                ev = json_mod.loads(line)
            except Exception:
                continue
            if ev.get("type") != "match":
                continue
            data = ev.get("data", {})
            path = data.get("path", {}).get("text", "")
            line_no = data.get("line_number", 0)
            text = data.get("lines", {}).get("text", "").rstrip("\n")
            matches.append({"path": path, "line": line_no, "snippet": text})
            if path not in files_seen and path:
                files_seen.add(path)
                try:
                    hashes[path] = file_content_hash(path)
                except Exception:
                    pass
        total = len(matches)  # ripgrep --max-count truncates; we lose exact total
        status = Status.OK if matches else Status.NO_RESULTS
        if total >= request.budget.max_results:
            status = Status.TRUNCATED
        return (
            {"matches": matches, "total_matches": total, "returned": len(matches)},
            status,
            hashes,
        )

    def _search_with_python(
        self,
        request: DispatchRequest,
        pattern: str,
        is_regex: bool,
        ctx_lines: int,
        deadline: float,
    ) -> tuple[dict, Status, dict[str, str]]:
        regex = re.compile(pattern) if is_regex else None
        all_files = iter_scoped_files(request.scope)
        root = Path(request.scope.root).resolve()
        matches = []
        total = 0
        hashes: dict[str, str] = {}
        files_searched = 0
        for fp in all_files:
            if time.monotonic() > deadline:
                status = Status.TIMEOUT if matches else Status.NO_RESULTS
                return (
                    {
                        "matches": matches,
                        "total_matches": total,
                        "returned": len(matches),
                        "files_searched": files_searched,
                    },
                    status,
                    hashes,
                )
            files_searched += 1
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except Exception:
                continue
            file_added = False
            for i, line in enumerate(lines):
                hit = bool(regex.search(line)) if regex else (pattern in line)
                if not hit:
                    continue
                total += 1
                if len(matches) >= request.budget.max_results:
                    continue
                ctx_before = [
                    lines[j].rstrip("\n")
                    for j in range(max(0, i - ctx_lines), i)
                ]
                ctx_after = [
                    lines[j].rstrip("\n")
                    for j in range(i + 1, min(len(lines), i + 1 + ctx_lines))
                ]
                matches.append(
                    {
                        "path": str(fp.relative_to(root)),
                        "line": i + 1,
                        "snippet": line.rstrip("\n"),
                        "context_before": ctx_before,
                        "context_after": ctx_after,
                    }
                )
                if not file_added:
                    try:
                        hashes[str(fp.relative_to(root))] = file_content_hash(str(fp))
                        file_added = True
                    except Exception:
                        pass
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
                "files_searched": files_searched,
            },
            status,
            hashes,
        )

    def _count_matches(
        self, request: DispatchRequest, deadline: float
    ) -> tuple[dict, Status, dict[str, str]]:
        pattern = request.params.get("pattern", "")
        if len(pattern) > MAX_PATTERN_LEN:
            raise ValueError("pattern too long")
        is_regex = bool(request.params.get("regex", False))
        regex = re.compile(pattern) if is_regex else None
        all_files = iter_scoped_files(request.scope)
        root = Path(request.scope.root).resolve()
        counts: dict[str, int] = {}
        for fp in all_files:
            if time.monotonic() > deadline:
                return ({"counts": counts, "partial": True}, Status.TIMEOUT, {})
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except Exception:
                continue
            if regex:
                c = len(regex.findall(text))
            else:
                c = text.count(pattern)
            if c:
                counts[str(fp.relative_to(root))] = c
        return ({"counts": counts, "partial": False},
                Status.OK if counts else Status.NO_RESULTS, {})

    def _error_report(
        self,
        request: DispatchRequest,
        started_at: str,
        start_mono: float,
        message: str,
    ) -> DispatchReport:
        return DispatchReport(
            request_id=request.request_id,
            subagent=self.class_name,
            task=request.task,
            status=Status.ERROR,
            result={},
            started_at=started_at,
            completed_at=utc_now_iso(),
            elapsed_ms=self._elapsed_ms(start_mono),
            error_message=message,
        )
