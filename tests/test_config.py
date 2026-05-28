from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def no_home_env(monkeypatch):
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("HERMES_PROVIDER", raising=False)
    monkeypatch.delenv("HERMES_MODEL", raising=False)


class TestLoadConfigDefaults:
    def test_load_returns_defaults_when_no_files_exist(self, tmp_path, no_home_env):
        from hermes_prime.config import load_config

        config = load_config(tmp_path)
        assert config["provider"] == ""
        assert config["model"] == "mistral"
        assert config["ollama_url"] == "http://localhost:11434"
        assert config["vllm_url"] == "http://localhost:8000"
        assert config["temperature"] == 0.7
        assert config["max_tokens"] == 2048
        assert "Hermes Prime" in config["system_prompt"]
        assert config["workspace_root"] == str(tmp_path.resolve())

    def test_load_without_workspace_root_uses_cwd(self, no_home_env):
        from hermes_prime.config import load_config

        config = load_config()
        assert config["workspace_root"] == str(Path.cwd())

    def test_load_with_none_workspace_root_uses_cwd(self, no_home_env):
        from hermes_prime.config import load_config

        config = load_config(None)
        assert config["workspace_root"] == str(Path.cwd())


class TestLoadConfigMerging:
    def test_home_config_is_loaded(self, tmp_path, monkeypatch):
        home_dir = tmp_path / ".hermes"
        home_dir.mkdir()
        (home_dir / "config.yaml").write_text("provider: ollama\nmodel: llama3\n")
        monkeypatch.setenv("HERMES_HOME", str(home_dir))
        monkeypatch.delenv("HERMES_PROVIDER", raising=False)
        monkeypatch.delenv("HERMES_MODEL", raising=False)

        from hermes_prime.config import load_config

        config = load_config(tmp_path)
        assert config["provider"] == "ollama"
        assert config["model"] == "llama3"

    def test_workspace_config_overrides_home(self, tmp_path, monkeypatch):
        home_dir = tmp_path / ".hermes"
        home_dir.mkdir()
        (home_dir / "config.yaml").write_text("provider: ollama\nmodel: llama3\n")
        monkeypatch.setenv("HERMES_HOME", str(home_dir))
        monkeypatch.delenv("HERMES_PROVIDER", raising=False)
        monkeypatch.delenv("HERMES_MODEL", raising=False)

        ws_dir = tmp_path / ".hermes-prime"
        ws_dir.mkdir(parents=True)
        (ws_dir / "config.yaml").write_text("model: gpt-4\n")

        from hermes_prime.config import load_config

        config = load_config(tmp_path)
        assert config["provider"] == "ollama"
        assert config["model"] == "gpt-4"

    def test_no_workspace_config_does_not_crash(self, tmp_path, monkeypatch):
        home_dir = tmp_path / ".hermes"
        home_dir.mkdir()
        (home_dir / "config.yaml").write_text("provider: ollama\n")
        monkeypatch.setenv("HERMES_HOME", str(home_dir))
        monkeypatch.delenv("HERMES_PROVIDER", raising=False)
        monkeypatch.delenv("HERMES_MODEL", raising=False)

        from hermes_prime.config import load_config

        config = load_config(tmp_path)
        assert config["provider"] == "ollama"

    def test_invalid_yaml_in_home_is_ignored(self, tmp_path, monkeypatch):
        home_dir = tmp_path / ".hermes"
        home_dir.mkdir()
        (home_dir / "config.yaml").write_text("{{invalid yaml\n")
        monkeypatch.setenv("HERMES_HOME", str(home_dir))
        monkeypatch.delenv("HERMES_PROVIDER", raising=False)
        monkeypatch.delenv("HERMES_MODEL", raising=False)

        from hermes_prime.config import load_config

        config = load_config(tmp_path)
        assert config["model"] == "mistral"

    def test_invalid_yaml_in_workspace_is_ignored(self, tmp_path, monkeypatch):
        monkeypatch.delenv("HERMES_PROVIDER", raising=False)
        monkeypatch.delenv("HERMES_MODEL", raising=False)

        ws_dir = tmp_path / ".hermes-prime"
        ws_dir.mkdir(parents=True)
        (ws_dir / "config.yaml").write_text("{{invalid\n")
        monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))

        from hermes_prime.config import load_config

        config = load_config(tmp_path)
        assert config["model"] == "mistral"


class TestLoadConfigEnvOverrides:
    def test_hermes_provider_env_var_overrides_file(self, tmp_path, monkeypatch):
        home_dir = tmp_path / ".hermes"
        home_dir.mkdir()
        (home_dir / "config.yaml").write_text("provider: ollama\n")
        monkeypatch.setenv("HERMES_HOME", str(home_dir))
        monkeypatch.setenv("HERMES_PROVIDER", "vllm")
        monkeypatch.delenv("HERMES_MODEL", raising=False)

        from hermes_prime.config import load_config

        config = load_config(tmp_path)
        assert config["provider"] == "vllm"

    def test_hermes_model_env_var_overrides_file(self, tmp_path, monkeypatch):
        home_dir = tmp_path / ".hermes"
        home_dir.mkdir()
        (home_dir / "config.yaml").write_text("model: llama3\n")
        monkeypatch.setenv("HERMES_HOME", str(home_dir))
        monkeypatch.setenv("HERMES_MODEL", "gpt-4")
        monkeypatch.delenv("HERMES_PROVIDER", raising=False)

        from hermes_prime.config import load_config

        config = load_config(tmp_path)
        assert config["model"] == "gpt-4"

    def test_env_vars_work_without_any_files(self, tmp_path, monkeypatch):
        monkeypatch.delenv("HERMES_HOME", raising=False)
        monkeypatch.setenv("HERMES_PROVIDER", "ollama")
        monkeypatch.setenv("HERMES_MODEL", "custom-model")

        from hermes_prime.config import load_config

        config = load_config(tmp_path)
        assert config["provider"] == "ollama"
        assert config["model"] == "custom-model"

    def test_empty_env_vars_do_not_override(self, tmp_path, monkeypatch):
        monkeypatch.delenv("HERMES_HOME", raising=False)
        monkeypatch.setenv("HERMES_PROVIDER", "")
        monkeypatch.setenv("HERMES_MODEL", "")

        from hermes_prime.config import load_config

        config = load_config(tmp_path)
        assert config["provider"] == ""
        assert config["model"] == "mistral"


class TestSaveConfig:
    def test_save_config_to_workspace(self, tmp_path):
        from hermes_prime.config import save_config

        result = save_config({"model": "llama3"}, workspace_root=tmp_path, global_=False)
        assert result["model"] == "llama3"

        ws_dir = tmp_path / ".hermes-prime"
        assert (ws_dir / "config.yaml").exists()
        content = (ws_dir / "config.yaml").read_text()
        assert "llama3" in content

    def test_save_config_to_global(self, tmp_path, monkeypatch):
        home_dir = tmp_path / ".hermes"
        monkeypatch.setenv("HERMES_HOME", str(home_dir))

        from hermes_prime.config import save_config

        result = save_config({"provider": "ollama"}, global_=True)
        assert result["provider"] == "ollama"
        assert (home_dir / "config.yaml").exists()

    def test_save_config_merges_with_existing(self, tmp_path):
        ws_dir = tmp_path / ".hermes-prime"
        ws_dir.mkdir(parents=True)
        (ws_dir / "config.yaml").write_text("provider: ollama\nmodel: mistral\n")

        from hermes_prime.config import save_config

        result = save_config({"model": "llama3"}, workspace_root=tmp_path, global_=False)
        assert result["provider"] == "ollama"
        assert result["model"] == "llama3"

    def test_save_config_returns_merged_dict(self, tmp_path):
        from hermes_prime.config import save_config

        result = save_config(
            {"provider": "vllm", "temperature": 0.5},
            workspace_root=tmp_path,
            global_=False,
        )
        assert result["provider"] == "vllm"
        assert result["temperature"] == 0.5

    def test_save_config_workspace_without_existing(self, tmp_path):
        from hermes_prime.config import save_config

        result = save_config({"model": "gpt-4"}, workspace_root=tmp_path, global_=False)
        assert result["model"] == "gpt-4"
        assert (tmp_path / ".hermes-prime" / "config.yaml").exists()
