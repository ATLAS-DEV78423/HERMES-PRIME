"""
Report validation: schema, size, provenance, injection scanning.

Every subagent report passes through validate_report() before reaching the
main agent's context. Quarantined reports do not surface.
"""

from __future__ import annotations

import re
from typing import Any

from refrlow.protocol import DispatchReport, DispatchRequest, Status


class ReportValidationError(Exception):
    """Raised when a report fails validation and is quarantined."""

    def __init__(self, report: DispatchReport, reason: str) -> None:
        super().__init__(f"Report {report.request_id} quarantined: {reason}")
        self.report = report
        self.reason = reason


# --- Injection-scanning patterns ---
#
# These are deliberately conservative. False positives are acceptable;
# they get tagged as warnings, not blocked. The main agent's CLAUDE.md
# instructs it to treat injection-warning fields with extra suspicion.

INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "imperative_to_ai",
        re.compile(
            r"\b(?:ai\s+(?:assistant|agent|model)|system)\s*[:,]?\s*"
            r"(?:you|please|now|ignore|forget|disregard)",
            re.IGNORECASE,
        ),
    ),
    (
        "ignore_prior",
        re.compile(
            r"\b(?:ignore|forget|disregard)\s+(?:all\s+|the\s+)?"
            r"(?:prior|previous|earlier|above)\s+(?:instructions?|context|messages?)",
            re.IGNORECASE,
        ),
    ),
    (
        "authorization_claim",
        re.compile(
            r"\b(?:user|admin|operator)\s+(?:has\s+)?(?:authorized|approved|granted|permitted)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "exfil_request",
        re.compile(
            r"\b(?:post|send|upload|exfiltrate|leak|transmit)\s+"
            r"(?:the\s+|all\s+|your\s+)?(?:token|secret|key|credential|password)",
            re.IGNORECASE,
        ),
    ),
    (
        "system_message_mimic",
        re.compile(r"<\s*(?:system|assistant|user)\s*>", re.IGNORECASE),
    ),
]


# --- Secret patterns (high-entropy markers) ---

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("gcp_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("github_token", re.compile(r"\bghp_[0-9A-Za-z]{36}\b")),
    ("github_fine_grained", re.compile(r"\bgithub_pat_[0-9A-Za-z_]{82}\b")),
    ("openai_key", re.compile(r"\bsk-[0-9A-Za-z]{20,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[0-9A-Za-z\-_]{20,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")),
    ("private_key_pem", re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----")),
]


def scan_text_for_injection(text: str) -> list[str]:
    """Return list of pattern names that matched the text."""
    matches = []
    for name, pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            matches.append(name)
    return matches


def scan_text_for_secrets(text: str) -> list[str]:
    """Return list of secret pattern names that matched the text."""
    matches = []
    for name, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            matches.append(name)
    return matches


def walk_text_fields(obj: Any, prefix: str = "") -> list[tuple[str, str]]:
    """Yield (path, value) for every string in a nested structure."""
    pairs: list[tuple[str, str]] = []
    if isinstance(obj, str):
        pairs.append((prefix, obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            pairs.extend(walk_text_fields(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            pairs.extend(walk_text_fields(item, f"{prefix}[{i}]"))
    return pairs


def validate_report(report: DispatchReport, request: DispatchRequest) -> DispatchReport:
    """
    Validate a subagent report. Mutates report.diagnostics with warnings.
    Raises ReportValidationError if the report must be quarantined.

    The validation pipeline:
      1. Status must be present and known.
      2. Report request_id must match request.
      3. Subagent/task must match request.
      4. Size must be under budget.
      5. Provenance must be present for non-error reports.
      6. Text fields scanned for injection and secret patterns.
    """

    # 1. Status sanity.
    if not isinstance(report.status, Status):
        raise ReportValidationError(report, "missing or invalid status")

    # 2. Request ID match.
    if report.request_id != request.request_id:
        raise ReportValidationError(
            report,
            f"request_id mismatch: expected {request.request_id}, "
            f"got {report.request_id}",
        )

    # 3. Subagent/task match.
    if report.subagent != request.subagent or report.task != request.task:
        raise ReportValidationError(
            report,
            f"subagent/task mismatch: expected {request.subagent}.{request.task}, "
            f"got {report.subagent}.{report.task}",
        )

    # 4. Size check (approximate token estimate as bytes/4).
    import json

    report_json = json.dumps(report.to_dict(), default=str)
    estimated_tokens = len(report_json) // 4
    if estimated_tokens > request.budget.max_tokens:
        # Don't quarantine; just downgrade status if it claims success.
        if report.status == Status.OK:
            report.status = Status.TRUNCATED
            report.diagnostics.warnings.append(
                f"report exceeded max_tokens ({estimated_tokens} > "
                f"{request.budget.max_tokens}); status downgraded to truncated"
            )

    # 5. Provenance check for non-error reports.
    if report.status in (Status.OK, Status.TRUNCATED) and not report.integrity:
        raise ReportValidationError(report, "missing integrity/provenance")

    # 6. Scan text fields for injection and secret patterns.
    text_fields = walk_text_fields(report.result)
    injection_hits: dict[str, list[str]] = {}
    secret_hits: dict[str, list[str]] = {}

    for path, value in text_fields:
        if hits := scan_text_for_injection(value):
            injection_hits[path] = hits
        if hits := scan_text_for_secrets(value):
            secret_hits[path] = hits

    if injection_hits:
        report.diagnostics.warnings.append(
            f"injection patterns detected in fields: "
            f"{', '.join(injection_hits.keys())}"
        )
        # Tag inside result for the main agent to see.
        report.result["_injection_warning"] = injection_hits

    if secret_hits:
        # Secret leakage is more serious. Redact and warn loudly.
        report.diagnostics.warnings.append(
            f"SECRET PATTERNS DETECTED in fields: "
            f"{', '.join(secret_hits.keys())}. Report quarantined."
        )
        raise ReportValidationError(
            report,
            f"secret patterns in report fields: {list(secret_hits.keys())}",
        )

    return report
