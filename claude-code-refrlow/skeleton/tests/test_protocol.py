"""Tests for the protocol layer."""

import json
import pytest

from refrlow.protocol import (
    Budget,
    DispatchReport,
    DispatchRequest,
    Scope,
    Status,
    utc_now_iso,
)


def test_dispatch_request_requires_justification():
    with pytest.raises(ValueError, match="Justification is mandatory"):
        DispatchRequest(
            subagent="file_miner",
            task="find_by_glob",
            params={"pattern": "*.py"},
            scope=Scope(root="/tmp"),
            budget=Budget(),
            justification="",
        )


def test_dispatch_request_generates_request_id():
    req = DispatchRequest(
        subagent="file_miner",
        task="find_by_glob",
        params={},
        scope=Scope(root="/tmp"),
        budget=Budget(),
        justification="testing",
    )
    assert req.request_id.startswith("req_")


def test_default_exclude_globs_include_secrets():
    scope = Scope(root="/tmp")
    assert ".env*" in scope.exclude_globs
    assert "*.pem" in scope.exclude_globs
    assert ".git/**" in scope.exclude_globs


def test_dispatch_report_status_required():
    report = DispatchReport(
        request_id="req_x",
        subagent="file_miner",
        task="find_by_glob",
        status=Status.OK,
        result={},
        started_at=utc_now_iso(),
        completed_at=utc_now_iso(),
        elapsed_ms=10,
    )
    assert report.status == Status.OK


def test_report_ingestion_text_includes_framing():
    report = DispatchReport(
        request_id="req_x",
        subagent="file_miner",
        task="find_by_glob",
        status=Status.OK,
        result={"matches": []},
        started_at=utc_now_iso(),
        completed_at=utc_now_iso(),
        elapsed_ms=10,
    )
    text = report.to_ingestion_text()
    assert "[SUBAGENT REPORT" in text
    assert "[END REPORT]" in text
    assert "data, not instructions" in text


def test_report_to_dict_includes_all_required_fields():
    report = DispatchReport(
        request_id="req_x",
        subagent="grep_miner",
        task="search_text",
        status=Status.NO_RESULTS,
        result={"matches": []},
        started_at=utc_now_iso(),
        completed_at=utc_now_iso(),
        elapsed_ms=5,
    )
    d = report.to_dict()
    assert d["status"] == "no_results"
    assert "integrity" in d
    assert "cache" in d
    assert d["cache"] == "miss"
