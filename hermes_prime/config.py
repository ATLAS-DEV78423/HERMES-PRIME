from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_CONFIG_FILE_NAME = "config.yaml"


def _home_dir() -> Path:
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def _workspace_dir(workspace_root: str | Path | None = None) -> Path:
    root = Path(workspace_root).resolve() if workspace_root else Path.cwd()
    return root / ".hermes-prime"


def load_config(workspace_root: str | Path | None = None) -> dict[str, Any]:
    """Load config from HERMES_HOME/config.yaml, then workspace/.hermes-prime/config.yaml merged over top."""
    config: dict[str, Any] = {
        "provider": "",
        "model": "mistral",
        "ollama_url": "http://localhost:11434",
        "vllm_url": "http://localhost:8000",
        "temperature": 0.7,
        "max_tokens": 2048,
        "system_prompt": "You are Hermes Prime, an intelligent AI assistant with access to tools.",
        "workspace_root": str(Path(workspace_root).resolve() if workspace_root else Path.cwd()),
    }

    _merge_yaml(_home_dir() / _CONFIG_FILE_NAME, config)

    if workspace_root:
        _merge_yaml(_workspace_dir(workspace_root) / _CONFIG_FILE_NAME, config)

    provider = os.environ.get("HERMES_PROVIDER")
    if provider:
        config["provider"] = provider
    model = os.environ.get("HERMES_MODEL")
    if model:
        config["model"] = model

    return config


def save_config(
    updates: dict[str, Any],
    workspace_root: str | Path | None = None,
    global_: bool = False,
) -> dict[str, Any]:
    """Save config updates to HERMES_HOME/config.yaml (global) or workspace/.hermes-prime/config.yaml."""
    target = _home_dir() if global_ else _workspace_dir(workspace_root)
    target.mkdir(parents=True, exist_ok=True)
    path = target / _CONFIG_FILE_NAME

    existing: dict[str, Any] = {}
    if path.exists():
        import yaml
        existing = yaml.safe_load(path.read_text()) or {}

    existing.update(updates)

    import yaml
    with open(path, "w") as f:
        yaml.dump(existing, f, default_flow_style=False)
    return existing


def _merge_yaml(path: Path, config: dict[str, Any]) -> None:
    if not path.exists():
        return
    try:
        import yaml
        data = yaml.safe_load(path.read_text())
        if isinstance(data, dict):
            config.update(data)
    except Exception:
        pass
