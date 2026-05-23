"""Tests for the FileMiner subagent and dispatcher integration."""

import os
import tempfile
from pathlib import Path

import pytest

from refrlow.dispatcher import Dispatcher, DispatchPolicy
from refrlow.miners.file_miner import FileMiner
from refrlow.miners.grep_miner import GrepMiner
from refrlow.protocol import Budget, DispatchRequest, Scope, Status


@pytest.fixture
def workspace():
    """Create a small temporary workspace with a few files."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "src").mkdir()
        (root / "src" / "a.py").write_text("def alpha():\n    return 1\n")
        (root / "src" / "b.py").write_text("def beta():\n    return alpha() + 1\n")
        (root / "src" / "c.ts").write_text("export const x = 1;\n")
        (root / "README.md").write_text("# project\n")
        # Should be excluded by default.
        (root / ".env").write_text("SECRET=hunter2\n")
        yield str(root)


def test_file_miner_find_by_glob(workspace):
    miner = FileMiner()
    req = DispatchRequest(
        subagent="file_miner",
        task="find_by_glob",
        params={"pattern": "**/*.py"},
        scope=Scope(root=workspace),
        budget=Budget(max_results=10, ttl_seconds=5),
        justification="find python files",
    )
    report = miner.execute(req)
    assert report.status == Status.OK
    paths = [m["path"] for m in report.result["matches"]]
    assert "src/a.py" in paths
    assert "src/b.py" in paths
    assert "src/c.ts" not in paths


def test_file_miner_respects_exclude_globs(workspace):
    miner = FileMiner()
    req = DispatchRequest(
        subagent="file_miner",
        task="find_by_glob",
        params={"pattern": "**/*"},
        scope=Scope(root=workspace),  # default excludes apply
        budget=Budget(max_results=100, ttl_seconds=5),
        justification="enumerate all (but excluded should be hidden)",
    )
    report = miner.execute(req)
    paths = [m["path"] for m in report.result["matches"]]
    assert ".env" not in paths


def test_dispatcher_blocks_out_of_workspace():
    pol = DispatchPolicy()
    disp = Dispatcher(policy=pol, workspace_root="/safe/workspace")
    disp.register(FileMiner())
    disp.begin_turn()

    req = DispatchRequest(
        subagent="file_miner",
        task="find_by_glob",
        params={"pattern": "*"},
        scope=Scope(root="/etc"),  # outside!
        budget=Budget(),
        justification="attempt out-of-workspace",
    )
    report = disp.dispatch(req)
    assert report.status == Status.DENIED
    assert report.denial_reason == "scope_outside_workspace"


def test_dispatcher_blocks_unknown_class():
    pol = DispatchPolicy()
    disp = Dispatcher(policy=pol, workspace_root="/tmp")
    disp.begin_turn()

    req = DispatchRequest(
        subagent="secret_fetcher",  # not registered, and never should be
        task="get_token",
        params={},
        scope=Scope(root="/tmp"),
        budget=Budget(),
        justification="attempt forbidden class",
    )
    report = disp.dispatch(req)
    assert report.status == Status.DENIED
    assert report.denial_reason == "unknown_subagent_class"


def test_dispatcher_enforces_per_turn_dispatch_cap(workspace):
    pol = DispatchPolicy(max_dispatches_per_turn=2)
    disp = Dispatcher(policy=pol, workspace_root=workspace)
    disp.register(FileMiner())
    disp.begin_turn()

    for _ in range(2):
        req = DispatchRequest(
            subagent="file_miner",
            task="find_by_glob",
            params={"pattern": "*.py"},
            scope=Scope(root=workspace),
            budget=Budget(max_tokens=200),
            justification="ok dispatch",
        )
        report = disp.dispatch(req)
        assert report.status != Status.DENIED

    # Third dispatch should be denied.
    req = DispatchRequest(
        subagent="file_miner",
        task="find_by_glob",
        params={"pattern": "*.py"},
        scope=Scope(root=workspace),
        budget=Budget(max_tokens=200),
        justification="over limit",
    )
    report = disp.dispatch(req)
    assert report.status == Status.DENIED
    assert report.denial_reason == "dispatch_count_exceeded"


def test_dispatcher_enforces_per_turn_token_budget(workspace):
    """A request whose budget would exceed per-turn cap is denied early."""
    pol = DispatchPolicy(max_tokens_per_turn=1000)
    disp = Dispatcher(policy=pol, workspace_root=workspace)
    disp.register(FileMiner())
    disp.begin_turn()

    req = DispatchRequest(
        subagent="file_miner",
        task="find_by_glob",
        params={"pattern": "*.py"},
        scope=Scope(root=workspace),
        budget=Budget(max_tokens=99999),  # too big
        justification="attempt to blow token budget",
    )
    report = disp.dispatch(req)
    assert report.status == Status.DENIED
    assert report.denial_reason == "dispatch_token_budget_exceeded"


def test_dispatcher_clamps_budget_to_class_cap(workspace):
    """A request within per-turn budget but over class cap gets clamped."""
    pol = DispatchPolicy(max_tokens_per_turn=100_000)
    # Override class cap to a small value.
    pol.max_budget_per_class["file_miner"] = Budget(
        max_tokens=500, max_results=3, max_bytes_per_result=512, ttl_seconds=2
    )
    disp = Dispatcher(policy=pol, workspace_root=workspace)
    disp.register(FileMiner())
    disp.begin_turn()

    req = DispatchRequest(
        subagent="file_miner",
        task="find_by_glob",
        params={"pattern": "**/*"},
        scope=Scope(root=workspace),
        # Reasonable per-turn-wise but over the class cap.
        budget=Budget(max_tokens=2000, max_results=100, ttl_seconds=10),
        justification="try to exceed class cap",
    )
    report = disp.dispatch(req)
    # Should run (within per-turn budget) but result must be clamped.
    assert report.status in (Status.OK, Status.TRUNCATED, Status.NO_RESULTS)
    assert len(report.result.get("matches", [])) <= 3


def test_grep_miner_finds_pattern(workspace):
    miner = GrepMiner()
    req = DispatchRequest(
        subagent="grep_miner",
        task="search_text",
        params={"pattern": "alpha"},
        scope=Scope(root=workspace),
        budget=Budget(max_results=10, ttl_seconds=5),
        justification="find references to alpha",
    )
    report = miner.execute(req)
    # alpha appears in both a.py (definition) and b.py (call).
    assert report.status in (Status.OK, Status.TRUNCATED)
    paths = {m["path"] for m in report.result["matches"]}
    assert "src/a.py" in paths
    assert "src/b.py" in paths
