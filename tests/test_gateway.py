from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _load_gateway_module():
    """Load hermes_prime/gateway.py as a module (shadowed by gateway/ package)."""
    path = Path(__file__).parent.parent / "hermes_prime" / "gateway.py"
    spec = importlib.util.spec_from_file_location("hermes_prime._gateway_mod", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hermes_prime._gateway_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


def _patch_upstream(modules: dict[str, types.ModuleType]):
    parent_chain: dict[str, types.ModuleType] = {}
    for path, mod in modules.items():
        parts = path.split(".")
        for i in range(1, len(parts)):
            parent = ".".join(parts[:i])
            if parent not in parent_chain and parent not in sys.modules:
                pkg = types.ModuleType(parent)
                pkg.__package__ = parent
                pkg.__path__ = [f"/fake/{parent.replace('.', '/')}"]
                parent_chain[parent] = pkg
    to_inject = {**parent_chain, **modules}
    return patch.dict("sys.modules", to_inject, clear=False)


@pytest.fixture
def manager(tmp_path: Path):
    mod = _load_gateway_module()
    return mod.GatewayManager(tmp_path, sentinel=None, trust_store=None)


# --- start ---

def test_start_success(manager) -> None:
    mock_run = MagicMock()
    gw_mod = types.ModuleType("gateway.run")
    gw_mod.__package__ = "gateway.run"
    gw_mod.run_gateway = mock_run
    with _patch_upstream({"gateway.run": gw_mod}):
        result = manager.start(platforms=["slack", "discord"])
    mock_run.assert_called_once_with(platforms=["slack", "discord"])
    assert result == {"status": "started", "platforms": ["slack", "discord"]}
    assert manager._running is True
    assert manager._thread is not None


def test_start_default_platforms(manager) -> None:
    mock_run = MagicMock()
    gw_mod = types.ModuleType("gateway.run")
    gw_mod.__package__ = "gateway.run"
    gw_mod.run_gateway = mock_run
    with _patch_upstream({"gateway.run": gw_mod}):
        result = manager.start()
    mock_run.assert_called_once_with(platforms=["slack"])
    assert result == {"status": "started", "platforms": ["slack"]}


def test_start_already_running(manager) -> None:
    mock_run = MagicMock()
    gw_mod = types.ModuleType("gateway.run")
    gw_mod.__package__ = "gateway.run"
    gw_mod.run_gateway = mock_run
    manager._running = True
    with _patch_upstream({"gateway.run": gw_mod}):
        result = manager.start(platforms=["slack"])
    mock_run.assert_not_called()
    assert result == {"status": "already running", "platforms": ["slack"]}


def test_start_import_error(manager) -> None:
    for k in list(sys.modules):
        if k.startswith("gateway"):
            del sys.modules[k]
    result = manager.start()
    assert result == {"error": "Upstream gateway not available"}
    assert manager._running is False


def test_start_exception(manager) -> None:
    gw_mod = types.ModuleType("gateway.run")
    gw_mod.__package__ = "gateway.run"
    gw_mod.run_gateway = MagicMock()
    with _patch_upstream({"gateway.run": gw_mod}):
        with patch("hermes_prime._gateway_mod.threading.Thread") as mock_thread:
            mock_thread.side_effect = RuntimeError("thread creation failed")
            result = manager.start()
    assert result == {"error": "thread creation failed"}
    assert manager._running is False


# --- stop ---

def test_stop_success(manager) -> None:
    mock_stop = MagicMock()
    gw_mod = types.ModuleType("gateway.run")
    gw_mod.__package__ = "gateway.run"
    gw_mod.stop_gateway = mock_stop
    manager._running = True
    with _patch_upstream({"gateway.run": gw_mod}):
        result = manager.stop()
    mock_stop.assert_called_once()
    assert result == {"status": "stopped"}
    assert manager._running is False


def test_stop_not_running(manager) -> None:
    mock_stop = MagicMock()
    gw_mod = types.ModuleType("gateway.run")
    gw_mod.__package__ = "gateway.run"
    gw_mod.stop_gateway = mock_stop
    with _patch_upstream({"gateway.run": gw_mod}):
        result = manager.stop()
    mock_stop.assert_not_called()
    assert result == {"status": "not running"}


def test_stop_import_error(manager) -> None:
    for k in list(sys.modules):
        if k.startswith("gateway"):
            del sys.modules[k]
    manager._running = True
    result = manager.stop()
    assert result == {"error": "Upstream gateway not available"}


# --- status ---

def test_status_success(manager) -> None:
    mock_status = MagicMock(return_value={"running": True, "connections": 2})
    gw_mod = types.ModuleType("gateway.run")
    gw_mod.__package__ = "gateway.run"
    gw_mod.gateway_status = mock_status
    with _patch_upstream({"gateway.run": gw_mod}):
        result = manager.status()
    assert result == {"running": True, "connections": 2}


def test_status_import_error(manager) -> None:
    for k in list(sys.modules):
        if k.startswith("gateway"):
            del sys.modules[k]
    result = manager.status()
    assert result == {"status": "upstream gateway not available"}


# --- list_platforms ---

def test_list_platforms_found(manager) -> None:
    platform_dir = (
        Path(__file__).parent.parent / "external" / "hermes-agent" / "gateway" / "platforms"
    )
    platform_dir.mkdir(parents=True, exist_ok=True)
    (platform_dir / "slack.py").write_text("# slack")
    (platform_dir / "discord.py").write_text("# discord")
    (platform_dir / "__init__.py").write_text("")
    (platform_dir / "_private.py").write_text("# internal")
    try:
        results = manager.list_platforms()
        names = {p["name"] for p in results}
        assert "slack" in names
        assert "discord" in names
        assert "__init__" not in names
        assert "_private" not in names
    finally:
        import shutil
        shutil.rmtree(platform_dir, ignore_errors=True)


def test_list_platforms_empty_dir(manager) -> None:
    platform_dir = (
        Path(__file__).parent.parent / "external" / "hermes-agent" / "gateway" / "platforms"
    )
    platform_dir.mkdir(parents=True, exist_ok=True)
    (platform_dir / "__init__.py").write_text("")
    try:
        results = manager.list_platforms()
        assert results == []
    finally:
        import shutil
        shutil.rmtree(platform_dir, ignore_errors=True)


def test_list_platforms_no_directory(manager) -> None:
    platform_dir = (
        Path(__file__).parent.parent / "external" / "hermes-agent" / "gateway" / "platforms"
    )
    platform_dir.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.rmtree(platform_dir)
    results = manager.list_platforms()
    assert results == [{"error": "Platforms directory not found"}]


def test_list_platforms_exception(manager) -> None:
    platform_dir = (
        Path(__file__).parent.parent / "external" / "hermes-agent" / "gateway" / "platforms"
    )
    platform_dir.mkdir(parents=True, exist_ok=True)
    (platform_dir / "slack.py").write_text("# slack")
    try:
        with patch("pathlib.Path.glob", side_effect=PermissionError("denied")):
            results = manager.list_platforms()
            assert results == [{"error": "denied"}]
    finally:
        import shutil
        shutil.rmtree(platform_dir, ignore_errors=True)


def test_thread_is_daemon(manager) -> None:
    mock_run = MagicMock()
    gw_mod = types.ModuleType("gateway.run")
    gw_mod.__package__ = "gateway.run"
    gw_mod.run_gateway = mock_run
    with _patch_upstream({"gateway.run": gw_mod}):
        manager.start(platforms=["slack"])
    assert manager._thread is not None
    assert manager._thread.daemon is True
