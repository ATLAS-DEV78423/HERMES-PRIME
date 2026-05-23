"""
Summarizer: compress files to structured summaries.

Hybrid subagent. Structural extraction (imports, exports, signatures) is
deterministic. Prose summaries (purpose_summary) require an LLM — the
reference implementation has a stub `_call_llm()` you replace with your
provider.

CRITICAL: any LLM-based summary path must use prompts/miner-system-prompt.md
as the system prompt to resist injection from file contents.
"""

from __future__ import annotations

import ast
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
from refrlow.reports import scan_text_for_injection


# Replace this with a call to your LLM provider (Haiku, local model, etc.).
# Must use the miner-system-prompt.md as the system prompt.
def _call_llm(file_content: str, max_words: int) -> str:
    """
    Stub. Real implementation should call a cheap model with the
    miner-system-prompt.md system prompt.
    """
    raise NotImplementedError(
        "Summarizer._call_llm is a stub. Wire up your LLM provider here "
        "(e.g., Anthropic Haiku, local Llama). Use "
        "prompts/miner-system-prompt.md as the system prompt."
    )


class Summarizer(Miner):
    class_name = "summarizer"
    tasks = {"signature_summary", "purpose_summary", "module_overview"}

    def execute(self, request: DispatchRequest) -> DispatchReport:
        start_mono, started_at = self._start()
        try:
            if request.task == "signature_summary":
                result, status, hashes = self._signature_summary(request)
                tokens = 0
            elif request.task == "module_overview":
                result, status, hashes = self._module_overview(request)
                tokens = 0
            elif request.task == "purpose_summary":
                result, status, hashes, tokens = self._purpose_summary(request)
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
            tokens_used=tokens,
            scope_searched=request.scope.to_dict(),
            integrity=Integrity(
                report_hash="sha256:pending", content_hashes=hashes
            ),
        )

    # --- task implementations ---

    def _signature_summary(
        self, request: DispatchRequest
    ) -> tuple[dict, Status, dict[str, str]]:
        path = request.params.get("path", "")
        root = Path(request.scope.root).resolve()
        fp = root / path
        if not fp.exists():
            return ({"path": path, "found": False}, Status.NO_RESULTS, {})

        # Python only in this reference impl.
        if fp.suffix != ".py":
            return ({"path": path, "supported": False,
                     "note": "reference impl supports .py only"},
                    Status.ERROR, {})

        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                src = f.read()
            tree = ast.parse(src, filename=str(fp))
        except Exception as exc:
            return ({"path": path, "parse_error": str(exc)},
                    Status.ERROR, {})

        imports = []
        exports = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                   ast.ClassDef)):
                if not node.name.startswith("_"):
                    exports.append(node.name)

        return (
            {
                "path": path,
                "imports": imports,
                "exports": exports,
                "lines": len(src.splitlines()),
            },
            Status.OK,
            {path: file_content_hash(str(fp))},
        )

    def _module_overview(
        self, request: DispatchRequest
    ) -> tuple[dict, Status, dict[str, str]]:
        paths = request.params.get("paths", [])
        root = Path(request.scope.root).resolve()
        overview = {}
        hashes = {}
        for path in paths:
            sub_req = DispatchRequest(
                subagent=self.class_name,
                task="signature_summary",
                params={"path": path},
                scope=request.scope,
                budget=request.budget,
                justification=request.justification,
                request_id=request.request_id,
            )
            result, status, sub_hashes = self._signature_summary(sub_req)
            if status == Status.OK:
                overview[path] = result
                hashes.update(sub_hashes)

        return ({"module_overview": overview}, Status.OK, hashes)

    def _purpose_summary(
        self, request: DispatchRequest
    ) -> tuple[dict, Status, dict[str, str], int]:
        path = request.params.get("path", "")
        max_words = int(request.params.get("max_words", 100))
        root = Path(request.scope.root).resolve()
        fp = root / path
        if not fp.exists():
            return ({"path": path, "found": False}, Status.NO_RESULTS, {}, 0)

        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        # Pre-scan source for injection patterns so the report carries the warning.
        injection_check = "passed"
        if scan_text_for_injection(content):
            injection_check = "flagged"

        # Call LLM (stub — replace with real provider).
        try:
            summary = _call_llm(content, max_words)
        except NotImplementedError:
            # Reference impl: produce a placeholder structural summary.
            sig_summary, _, _ = self._signature_summary(request)
            summary = (
                f"[Reference impl: LLM not wired up. Structural facts: "
                f"{len(sig_summary.get('imports', []))} imports, "
                f"{len(sig_summary.get('exports', []))} exports, "
                f"{sig_summary.get('lines', 0)} lines.]"
            )

        # Post-scan summary for forbidden imperative patterns.
        if scan_text_for_injection(summary):
            # Summary itself contains suspicious content; flag.
            injection_check = "flagged"

        return (
            {
                "path": path,
                "summary": summary,
                "word_count": len(summary.split()),
                "injection_check": injection_check,
                "model_used": "stub",
            },
            Status.ESCALATE if injection_check == "flagged" else Status.OK,
            {path: file_content_hash(str(fp))},
            # Tokens used would be returned by the LLM provider.
            0,
        )

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
