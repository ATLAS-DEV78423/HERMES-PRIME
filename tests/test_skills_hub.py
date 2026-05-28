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
    """Context manager that injects mock upstream modules into sys.modules."""
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
def manager(tmp_path: Path) -> "SkillsManager":
    from hermes_prime.skills_hub import SkillsManager

    return SkillsManager(tmp_path, sentinel=None, trust_store=None)


class MockSkillResult:
    def __init__(self, name: str, identifier: str, description: str = "", source: str = "github", trust_level: int = 1, version: str = "1.0"):
        self.name = name
        self.identifier = identifier
        self.description = description
        self.source = source
        self.trust_level = trust_level
        self.version = version


# --- search ---

def test_search_success(manager: "SkillsManager") -> None:
    mock_search = MagicMock(return_value=[
        MockSkillResult("skill_a", "id:a", "Does A", "github", 2, "1.0"),
        MockSkillResult("skill_b", "id:b", "Does B", "local", 3, "2.0"),
    ])
    hub = _mock_module("tools.skills_hub", unified_search=mock_search)
    with _patch_upstream({"tools.skills_hub": hub}):
        results = manager.search("test query", limit=10)
    mock_search.assert_called_once_with("test query", sources="all", source_filter="all", limit=10)
    assert len(results) == 2
    assert results[0]["name"] == "skill_a"
    assert results[0]["identifier"] == "id:a"
    assert results[0]["trust_level"] == 2
    assert results[1]["version"] == "2.0"


def test_search_empty_results(manager: "SkillsManager") -> None:
    mock_search = MagicMock(return_value=[])
    hub = _mock_module("tools.skills_hub", unified_search=mock_search)
    with _patch_upstream({"tools.skills_hub": hub}):
        results = manager.search("nothing", limit=20)
    assert results == []


def test_search_import_error(manager: "SkillsManager") -> None:
    blocked = {"tools": None, "tools.skills_hub": None}
    with patch.dict("sys.modules", blocked, clear=False):
        results = manager.search("query")
    assert results == [{"error": "Upstream skills hub not available"}]


# --- browse ---

def test_browse_success(manager: "SkillsManager") -> None:
    items = {"s1": MockSkillResult("s1", "id:1", "first", "github"), "s2": MockSkillResult("s2", "id:2", "second", "github")}
    mock_fetch = MagicMock(return_value=items)
    hub = _mock_module("tools.skills_hub", fetch_skill_index=mock_fetch)
    with _patch_upstream({"tools.skills_hub": hub}):
        results = manager.browse(page=1)
    assert len(results) == 2


def test_browse_pagination(manager: "SkillsManager") -> None:
    items = {f"s{i}": MockSkillResult(f"s{i}", f"id:{i}", "", "github") for i in range(50)}
    mock_fetch = MagicMock(return_value=items)
    hub = _mock_module("tools.skills_hub", fetch_skill_index=mock_fetch)
    with _patch_upstream({"tools.skills_hub": hub}):
        page1 = manager.browse(page=1)
        page2 = manager.browse(page=2)
    assert len(page1) == 20
    assert len(page2) == 20
    assert page1[0]["name"] != page2[0]["name"]


def test_browse_empty(manager: "SkillsManager") -> None:
    mock_fetch = MagicMock(return_value={})
    hub = _mock_module("tools.skills_hub", fetch_skill_index=mock_fetch)
    with _patch_upstream({"tools.skills_hub": hub}):
        results = manager.browse()
    assert results == []


def test_browse_import_error(manager: "SkillsManager") -> None:
    blocked = {"tools": None, "tools.skills_hub": None}
    with patch.dict("sys.modules", blocked, clear=False):
        results = manager.browse()
    assert results == [{"error": "Upstream skills hub not available"}]


# --- inspect ---

def test_inspect_with_to_dict(manager: "SkillsManager") -> None:
    mock_detail = MagicMock()
    mock_detail.to_dict.return_value = {"name": "test_skill", "version": "1.0"}
    mock_fetch = MagicMock(return_value=mock_detail)
    hub = _mock_module("tools.skills_hub", fetch_skill_detail=mock_fetch)
    with _patch_upstream({"tools.skills_hub": hub}):
        result = manager.inspect("test_skill")
    assert result == {"name": "test_skill", "version": "1.0"}


def test_inspect_with_dict(manager: "SkillsManager") -> None:
    mock_fetch = MagicMock(return_value={"key": "value", "nested": {"a": 1}})
    hub = _mock_module("tools.skills_hub", fetch_skill_detail=mock_fetch)
    with _patch_upstream({"tools.skills_hub": hub}):
        result = manager.inspect("test_skill")
    assert result == {"key": "value", "nested": {"a": 1}}


def test_inspect_with_string(manager: "SkillsManager") -> None:
    mock_fetch = MagicMock(return_value="raw content string")
    hub = _mock_module("tools.skills_hub", fetch_skill_detail=mock_fetch)
    with _patch_upstream({"tools.skills_hub": hub}):
        result = manager.inspect("test_skill")
    assert result == {"content": "raw content string"}


def test_inspect_import_error(manager: "SkillsManager") -> None:
    blocked = {"tools": None, "tools.skills_hub": None}
    with patch.dict("sys.modules", blocked, clear=False):
        result = manager.inspect("anything")
    assert result == {"error": "Upstream skills hub not available"}


# --- install ---

def test_install_success(manager: "SkillsManager") -> None:
    mock_install = MagicMock(return_value={"status": "ok", "id": "abc"})
    hub = _mock_module("tools.skills_hub", do_install_skill=mock_install)
    with _patch_upstream({"tools.skills_hub": hub}):
        with patch("hermes_prime.skills_hub.SkillsManager._audit") as mock_audit:
            result = manager.install("some-skill")
    assert result == {"status": "ok", "id": "abc"}
    mock_audit.assert_called_once_with("install", {"identifier": "some-skill", "result": str({"status": "ok", "id": "abc"})})


def test_install_non_dict_result(manager: "SkillsManager") -> None:
    mock_install = MagicMock(return_value="successfully installed")
    hub = _mock_module("tools.skills_hub", do_install_skill=mock_install)
    with _patch_upstream({"tools.skills_hub": hub}):
        with patch("hermes_prime.skills_hub.SkillsManager._audit"):
            result = manager.install("some-skill")
    assert result == {"status": "installed", "identifier": "some-skill", "detail": "successfully installed"}


def test_install_exception(manager: "SkillsManager") -> None:
    mock_install = MagicMock(side_effect=ValueError("permission denied"))
    hub = _mock_module("tools.skills_hub", do_install_skill=mock_install)
    with _patch_upstream({"tools.skills_hub": hub}):
        result = manager.install("some-skill")
    assert result == {"error": "permission denied"}


def test_install_import_error(manager: "SkillsManager") -> None:
    blocked = {"tools": None, "tools.skills_hub": None}
    with patch.dict("sys.modules", blocked, clear=False):
        result = manager.install("anything")
    assert result == {"error": "Upstream skills hub not available"}


# --- list_installed ---

def test_list_installed_success(manager: "SkillsManager") -> None:
    mock_skill = MagicMock()
    mock_skill.name = "local_skill"
    mock_skill.description = "A local skill"
    mock_skill.source = "local"
    mock_skill.version = "0.1"
    mock_discover = MagicMock(return_value=[mock_skill])
    utils = _mock_module("agent.skill_utils", discover_skills=mock_discover)
    with _patch_upstream({"agent.skill_utils": utils}):
        results = manager.list_installed()
    assert len(results) == 1
    assert results[0]["name"] == "local_skill"
    assert results[0]["description"] == "A local skill"
    assert results[0]["source"] == "local"


def test_list_installed_empty(manager: "SkillsManager") -> None:
    mock_discover = MagicMock(return_value=[])
    utils = _mock_module("agent.skill_utils", discover_skills=mock_discover)
    with _patch_upstream({"agent.skill_utils": utils}):
        results = manager.list_installed()
    assert results == []


def test_list_installed_import_error(manager: "SkillsManager") -> None:
    blocked = {"agent": None, "agent.skill_utils": None}
    with patch.dict("sys.modules", blocked, clear=False):
        results = manager.list_installed()
    assert results == [{"error": "Upstream skill discovery not available"}]


# --- uninstall ---

def test_uninstall_success(manager: "SkillsManager") -> None:
    mock_remove = MagicMock(return_value="removed")
    hub = _mock_module("tools.skills_hub", do_remove_skill=mock_remove)
    with _patch_upstream({"tools.skills_hub": hub}):
        with patch("hermes_prime.skills_hub.SkillsManager._audit") as mock_audit:
            result = manager.uninstall("some-skill")
    assert result == {"status": "uninstalled", "name": "some-skill"}
    mock_audit.assert_called_once_with("uninstall", {"name": "some-skill", "result": "removed"})


def test_uninstall_exception(manager: "SkillsManager") -> None:
    mock_remove = MagicMock(side_effect=RuntimeError("cannot remove"))
    hub = _mock_module("tools.skills_hub", do_remove_skill=mock_remove)
    with _patch_upstream({"tools.skills_hub": hub}):
        result = manager.uninstall("some-skill")
    assert result == {"error": "cannot remove"}


def test_uninstall_import_error(manager: "SkillsManager") -> None:
    blocked = {"tools": None, "tools.skills_hub": None}
    with patch.dict("sys.modules", blocked, clear=False):
        result = manager.uninstall("anything")
    assert result == {"error": "Upstream skills hub not available"}


# --- check_updates ---

def test_check_updates_success(manager: "SkillsManager") -> None:
    mock_r = MagicMock()
    mock_r.name = "skill_x"
    mock_check = MagicMock(return_value=[mock_r])
    hub = _mock_module("tools.skills_hub", check_skill_updates=mock_check)
    with _patch_upstream({"tools.skills_hub": hub}):
        results = manager.check_updates()
    assert len(results) == 1
    assert results[0]["name"] == "skill_x"
    assert results[0]["update_available"] is True


def test_check_updates_empty(manager: "SkillsManager") -> None:
    mock_check = MagicMock(return_value=[])
    hub = _mock_module("tools.skills_hub", check_skill_updates=mock_check)
    with _patch_upstream({"tools.skills_hub": hub}):
        results = manager.check_updates()
    assert results == []


def test_check_updates_import_error(manager: "SkillsManager") -> None:
    blocked = {"tools": None, "tools.skills_hub": None}
    with patch.dict("sys.modules", blocked, clear=False):
        results = manager.check_updates()
    assert results == [{"error": "Upstream skills hub not available"}]
