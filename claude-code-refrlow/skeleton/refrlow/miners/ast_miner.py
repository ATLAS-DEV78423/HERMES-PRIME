"""
AST Miner: language-aware symbol search.

Reference implementation uses Python's `ast` module for .py files. A real
deployment should wire up `tree-sitter` or `ast-grep` for multi-language
support. The protocol is the same; only the implementation differs.
"""

from __future__ import annotations

import ast
import re
import time
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


class AstMiner(Miner):
    class_name = "ast_miner"
    tasks = {
        "find_definition",
        "find_references",
        "find_callers_of",
        "extract_signatures",
    }

    def execute(self, request: DispatchRequest) -> DispatchReport:
        start_mono, started_at = self._start()
        deadline = start_mono + request.budget.ttl_seconds

        try:
            if request.task == "find_definition":
                result, status = self._find_definition(request, deadline)
            elif request.task == "find_references":
                result, status = self._find_references(request, deadline)
            elif request.task == "find_callers_of":
                result, status = self._find_callers_of(request, deadline)
            elif request.task == "extract_signatures":
                result, status = self._extract_signatures(request, deadline)
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
            integrity=Integrity(report_hash="sha256:pending"),
        )

    # --- Python-only reference implementations ---

    def _find_definition(
        self, request: DispatchRequest, deadline: float
    ) -> tuple[dict, Status]:
        symbol = request.params.get("symbol", "")
        if not symbol:
            raise ValueError("find_definition requires 'symbol' parameter")

        all_files = [f for f in iter_scoped_files(request.scope)
                     if f.suffix == ".py"]
        root = Path(request.scope.root).resolve()

        for fp in all_files:
            if time.monotonic() > deadline:
                return ({"found": False, "symbol": symbol, "timeout": True},
                        Status.TIMEOUT)
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    src = f.read()
                tree = ast.parse(src, filename=str(fp))
            except Exception:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef)) and node.name == symbol:
                    sig = self._render_signature(node)
                    docstring = ast.get_docstring(node) or ""
                    return (
                        {
                            "found": True,
                            "path": str(fp.relative_to(root)),
                            "line": node.lineno,
                            "column": node.col_offset,
                            "signature": sig,
                            "doc_comment": docstring,
                            "language": "python",
                        },
                        Status.OK,
                    )

        return (
            {"found": False, "symbol": symbol,
             "scope_searched": str(root)},
            Status.NO_RESULTS,
        )

    def _find_references(
        self, request: DispatchRequest, deadline: float
    ) -> tuple[dict, Status]:
        symbol = request.params.get("symbol", "")
        if not symbol:
            raise ValueError("find_references requires 'symbol' parameter")
        # Use regex over file contents as a cheap approximation.
        # A real AST-based version would walk Name and Attribute nodes.
        pattern = re.compile(rf"\b{re.escape(symbol)}\b")
        all_files = [f for f in iter_scoped_files(request.scope)
                     if f.suffix == ".py"]
        root = Path(request.scope.root).resolve()
        refs = []
        total = 0
        for fp in all_files:
            if time.monotonic() > deadline:
                break
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except Exception:
                continue
            for i, line in enumerate(lines):
                if pattern.search(line):
                    total += 1
                    if len(refs) < request.budget.max_results:
                        refs.append({
                            "path": str(fp.relative_to(root)),
                            "line": i + 1,
                            "snippet": line.rstrip("\n"),
                        })
        status = (
            Status.OK
            if total == len(refs)
            else Status.TRUNCATED
            if refs
            else Status.NO_RESULTS
        )
        return (
            {"references": refs, "total_references": total,
             "returned": len(refs)},
            status,
        )

    def _find_callers_of(
        self, request: DispatchRequest, deadline: float
    ) -> tuple[dict, Status]:
        function = request.params.get("function", "")
        if not function:
            raise ValueError("find_callers_of requires 'function' parameter")
        all_files = [f for f in iter_scoped_files(request.scope)
                     if f.suffix == ".py"]
        root = Path(request.scope.root).resolve()
        callers = []
        total = 0
        for fp in all_files:
            if time.monotonic() > deadline:
                break
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    src = f.read()
                tree = ast.parse(src, filename=str(fp))
            except Exception:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                called_name = None
                if isinstance(func, ast.Name):
                    called_name = func.id
                elif isinstance(func, ast.Attribute):
                    called_name = func.attr
                if called_name == function:
                    total += 1
                    if len(callers) < request.budget.max_results:
                        # Determine enclosing function (if any) — simple walk.
                        enclosing = self._find_enclosing_function(tree, node)
                        callers.append({
                            "path": str(fp.relative_to(root)),
                            "line": node.lineno,
                            "call_form": f"{function}(...)",
                            "in_function": enclosing,
                        })
        status = (
            Status.OK
            if total == len(callers)
            else Status.TRUNCATED
            if callers
            else Status.NO_RESULTS
        )
        return (
            {"callers": callers, "total_callers": total,
             "returned": len(callers)},
            status,
        )

    def _extract_signatures(
        self, request: DispatchRequest, deadline: float
    ) -> tuple[dict, Status]:
        path_param = request.params.get("path")
        paths_param = request.params.get("paths")
        if path_param:
            target_paths = [path_param]
        elif paths_param:
            target_paths = paths_param
        else:
            raise ValueError("extract_signatures requires 'path' or 'paths'")

        root = Path(request.scope.root).resolve()
        results: dict[str, list[dict]] = {}
        for relpath in target_paths:
            if time.monotonic() > deadline:
                return ({"signatures": results, "partial": True},
                        Status.TIMEOUT)
            fp = root / relpath
            if not fp.exists() or fp.suffix != ".py":
                continue
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    src = f.read()
                tree = ast.parse(src, filename=str(fp))
            except Exception:
                continue
            sigs = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef)):
                    sigs.append({
                        "name": node.name,
                        "kind": type(node).__name__,
                        "line": node.lineno,
                        "signature": self._render_signature(node),
                    })
            results[relpath] = sigs
        return ({"signatures": results, "partial": False}, Status.OK)

    # --- helpers ---

    @staticmethod
    def _render_signature(node: ast.AST) -> str:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in node.args.args]
            prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
            return f"{prefix}{node.name}({', '.join(args)})"
        if isinstance(node, ast.ClassDef):
            bases = []
            for b in node.bases:
                if isinstance(b, ast.Name):
                    bases.append(b.id)
                else:
                    bases.append("...")
            base_str = f"({', '.join(bases)})" if bases else ""
            return f"class {node.name}{base_str}"
        return ""

    @staticmethod
    def _find_enclosing_function(tree: ast.AST, target: ast.AST) -> str:
        # Walk parents — Python's ast doesn't track parents natively.
        # Build a parent map.
        parent_map: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parent_map[child] = parent

        node = target
        while node in parent_map:
            node = parent_map[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return node.name
        return "<module>"

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
