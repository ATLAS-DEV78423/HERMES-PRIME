from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _mock_module(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__package__ = name
    mod.__name__ = name
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


def _patch_upstream(modules: dict[str, types.ModuleType]):
    parent_chain: dict[str, types.ModuleType] = {}
    for path, mod in modules.items():
        parts = path.split(".")
        for i in range(1, len(parts)):
            parent = ".".join(parts[:i])
            if parent not in parent_chain and parent not in sys.modules:
                pkg = _mock_module(parent)
                pkg.__path__ = [f"/fake/{parent.replace('.', '/')}"]
                parent_chain[parent] = pkg
    to_inject = {**parent_chain, **modules}
    return patch.dict("sys.modules", to_inject, clear=False)


@pytest.fixture
def manager(tmp_path: Path) -> "CronManager":
    from hermes_prime.cron_jobs import CronManager

    return CronManager(tmp_path, sentinel=None, trust_store=None)


@pytest.fixture
def mock_jobs_module() -> types.ModuleType:
    return _mock_module("cron.jobs")


@pytest.fixture
def mock_scheduler_module() -> types.ModuleType:
    return _mock_module("cron.scheduler")


# --- list_jobs ---

def test_list_jobs_success(manager: "CronManager") -> None:
    mock_jobs_data = [
        {
            "id": "job-1",
            "name": "daily report",
            "schedule": {"cron": "0 9 * * *"},
            "schedule_display": "every day at 9am",
            "enabled": True,
            "skill": "report_gen",
            "skills": [],
            "model": "gpt4",
            "provider": "openai",
            "workdir": "/tmp",
            "next_run_at": "2026-06-01T09:00:00",
            "last_run_at": "",
            "last_result": None,
        }
    ]
    mock_list = MagicMock(return_value=mock_jobs_data)
    jobs_mod = _mock_module("cron.jobs", list_jobs=mock_list)
    with _patch_upstream({"cron.jobs": jobs_mod}):
        results = manager.list_jobs(include_disabled=False)
    mock_list.assert_called_once_with(include_disabled=False)
    assert len(results) == 1
    assert results[0]["id"] == "job-1"
    assert results[0]["state"] == "scheduled"
    assert results[0]["enabled"] is True


def test_list_jobs_paused_state(manager: "CronManager") -> None:
    mock_list = MagicMock(return_value=[
        {"id": "j1", "name": "paused job", "schedule": {}, "schedule_display": "", "enabled": False,
         "skill": "", "skills": [], "model": None, "provider": None, "workdir": None,
         "next_run_at": "", "last_run_at": "", "last_result": None}
    ])
    jobs_mod = _mock_module("cron.jobs", list_jobs=mock_list)
    with _patch_upstream({"cron.jobs": jobs_mod}):
        results = manager.list_jobs()
    assert results[0]["state"] == "paused"


def test_list_jobs_empty(manager: "CronManager") -> None:
    mock_list = MagicMock(return_value=[])
    jobs_mod = _mock_module("cron.jobs", list_jobs=mock_list)
    with _patch_upstream({"cron.jobs": jobs_mod}):
        results = manager.list_jobs()
    assert results == []


def test_list_jobs_import_error(manager: "CronManager") -> None:
    blocked = {"cron": None, "cron.jobs": None, "cron.scheduler": None}
    with patch.dict("sys.modules", blocked, clear=False):
        results = manager.list_jobs()
    assert results == [{"error": "Upstream cron not available"}]


# --- create_job ---

def test_create_job_success(manager: "CronManager") -> None:
    mock_add = MagicMock(return_value="new-job-id")
    jobs_mod = _mock_module("cron.jobs", add_job=mock_add)
    with _patch_upstream({"cron.jobs": jobs_mod}):
        with patch("hermes_prime.cron_jobs.CronManager._audit") as mock_audit:
            result = manager.create_job(
                name="my job", schedule="0 9 * * *", prompt="run me",
                model="gpt4", provider="openai", skills=["skill1"],
                workdir="/ws", deliver=["email"],
            )
    assert result == {"id": "new-job-id", "name": "my job", "status": "created"}
    mock_add.assert_called_once_with(
        name="my job", schedule="0 9 * * *", prompt="run me",
        model="gpt4", provider="openai", skills=["skill1"],
        workdir="/ws", deliver=["email"],
    )
    mock_audit.assert_called_once_with(
        "create", {"job_id": "new-job-id", "name": "my job", "schedule": "0 9 * * *"}
    )


def test_create_job_default_deliver(manager: "CronManager") -> None:
    mock_add = MagicMock(return_value="id")
    jobs_mod = _mock_module("cron.jobs", add_job=mock_add)
    with _patch_upstream({"cron.jobs": jobs_mod}):
        with patch("hermes_prime.cron_jobs.CronManager._audit"):
            manager.create_job(name="j", schedule="* * * * *", prompt="p")
    mock_add.assert_called_once_with(
        name="j", schedule="* * * * *", prompt="p",
        model=None, provider=None, skills=None, workdir=None, deliver=["local"],
    )


def test_create_job_exception(manager: "CronManager") -> None:
    mock_add = MagicMock(side_effect=RuntimeError("bad cron"))
    jobs_mod = _mock_module("cron.jobs", add_job=mock_add)
    with _patch_upstream({"cron.jobs": jobs_mod}):
        result = manager.create_job(name="j", schedule="bad", prompt="p")
    assert result == {"error": "bad cron"}


def test_create_job_import_error(manager: "CronManager") -> None:
    with patch.dict("sys.modules", {"cron": None, "cron.jobs": None, "cron.scheduler": None}, clear=False):
        result = manager.create_job(name="j", schedule="* * * * *", prompt="p")
    assert result == {"error": "Upstream cron not available"}


# --- edit_job ---

def test_edit_job_success(manager: "CronManager") -> None:
    mock_update = MagicMock()
    jobs_mod = _mock_module("cron.jobs", update_job=mock_update)
    with _patch_upstream({"cron.jobs": jobs_mod}):
        with patch("hermes_prime.cron_jobs.CronManager._audit") as mock_audit:
            result = manager.edit_job("job-1", name="new name", schedule="0 0 * * *")
    mock_update.assert_called_once_with("job-1", name="new name", schedule="0 0 * * *")
    assert result == {"id": "job-1", "status": "updated"}
    mock_audit.assert_called_once_with("edit", {"job_id": "job-1", "name": "new name", "schedule": "0 0 * * *"})


def test_edit_job_exception(manager: "CronManager") -> None:
    mock_update = MagicMock(side_effect=KeyError("job not found"))
    jobs_mod = _mock_module("cron.jobs", update_job=mock_update)
    with _patch_upstream({"cron.jobs": jobs_mod}):
        result = manager.edit_job("bad-id", name="x")
    assert result == {"error": "'job not found'"}


def test_edit_job_import_error(manager: "CronManager") -> None:
    with patch.dict("sys.modules", {"cron": None, "cron.jobs": None, "cron.scheduler": None}, clear=False):
        result = manager.edit_job("j1", name="x")
    assert result == {"error": "Upstream cron not available"}


# --- pause_job ---

def test_pause_job_success(manager: "CronManager") -> None:
    mock_pause = MagicMock()
    jobs_mod = _mock_module("cron.jobs", pause_job=mock_pause)
    with _patch_upstream({"cron.jobs": jobs_mod}):
        with patch("hermes_prime.cron_jobs.CronManager._audit") as mock_audit:
            result = manager.pause_job("job-1")
    mock_pause.assert_called_once_with("job-1")
    assert result == {"id": "job-1", "status": "paused"}
    mock_audit.assert_called_once_with("pause", {"job_id": "job-1"})


def test_pause_job_import_error(manager: "CronManager") -> None:
    with patch.dict("sys.modules", {"cron": None, "cron.jobs": None, "cron.scheduler": None}, clear=False):
        result = manager.pause_job("j1")
    assert result == {"error": "Upstream cron not available"}


# --- resume_job ---

def test_resume_job_success(manager: "CronManager") -> None:
    mock_resume = MagicMock()
    jobs_mod = _mock_module("cron.jobs", resume_job=mock_resume)
    with _patch_upstream({"cron.jobs": jobs_mod}):
        with patch("hermes_prime.cron_jobs.CronManager._audit") as mock_audit:
            result = manager.resume_job("job-1")
    mock_resume.assert_called_once_with("job-1")
    assert result == {"id": "job-1", "status": "resumed"}
    mock_audit.assert_called_once_with("resume", {"job_id": "job-1"})


def test_resume_job_import_error(manager: "CronManager") -> None:
    with patch.dict("sys.modules", {"cron": None, "cron.jobs": None, "cron.scheduler": None}, clear=False):
        result = manager.resume_job("j1")
    assert result == {"error": "Upstream cron not available"}


# --- run_job ---

def test_run_job_success(manager: "CronManager") -> None:
    mock_trigger = MagicMock()
    jobs_mod = _mock_module("cron.jobs", trigger_job=mock_trigger)
    with _patch_upstream({"cron.jobs": jobs_mod}):
        with patch("hermes_prime.cron_jobs.CronManager._audit") as mock_audit:
            result = manager.run_job("job-1")
    mock_trigger.assert_called_once_with("job-1")
    assert result == {"id": "job-1", "status": "triggered"}
    mock_audit.assert_called_once_with("run", {"job_id": "job-1"})


def test_run_job_import_error(manager: "CronManager") -> None:
    with patch.dict("sys.modules", {"cron": None, "cron.jobs": None, "cron.scheduler": None}, clear=False):
        result = manager.run_job("j1")
    assert result == {"error": "Upstream cron not available"}


# --- remove_job ---

def test_remove_job_success(manager: "CronManager") -> None:
    mock_remove = MagicMock()
    jobs_mod = _mock_module("cron.jobs", remove_job=mock_remove)
    with _patch_upstream({"cron.jobs": jobs_mod}):
        with patch("hermes_prime.cron_jobs.CronManager._audit") as mock_audit:
            result = manager.remove_job("job-1")
    mock_remove.assert_called_once_with("job-1")
    assert result == {"id": "job-1", "status": "removed"}
    mock_audit.assert_called_once_with("remove", {"job_id": "job-1"})


def test_remove_job_import_error(manager: "CronManager") -> None:
    with patch.dict("sys.modules", {"cron": None, "cron.jobs": None, "cron.scheduler": None}, clear=False):
        result = manager.remove_job("j1")
    assert result == {"error": "Upstream cron not available"}


# --- scheduler_status ---

def test_scheduler_status_success(manager: "CronManager") -> None:
    mock_status = MagicMock(return_value={"running": True, "active_jobs": 3})
    sched_mod = _mock_module("cron.scheduler", scheduler_status=mock_status)
    with _patch_upstream({"cron.scheduler": sched_mod}):
        result = manager.scheduler_status()
    assert result == {"running": True, "active_jobs": 3}


def test_scheduler_status_import_error(manager: "CronManager") -> None:
    with patch.dict("sys.modules", {"cron": None, "cron.jobs": None, "cron.scheduler": None}, clear=False):
        result = manager.scheduler_status()
    assert result == {"status": "upstream cron not available"}


# --- tick ---

def test_tick_success(manager: "CronManager") -> None:
    mock_tick = MagicMock(return_value={"triggered": ["job-1"]})
    sched_mod = _mock_module("cron.scheduler", tick=mock_tick)
    with _patch_upstream({"cron.scheduler": sched_mod}):
        result = manager.tick()
    assert result == {"status": "tick completed", "result": str({"triggered": ["job-1"]})}


def test_tick_import_error(manager: "CronManager") -> None:
    with patch.dict("sys.modules", {"cron": None, "cron.jobs": None, "cron.scheduler": None}, clear=False):
        result = manager.tick()
    assert result == {"error": "Upstream cron not available"}
