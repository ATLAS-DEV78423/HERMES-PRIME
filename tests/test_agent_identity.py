from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest


class TestAgentIdentityLoadCreate:
    def test_creates_identity_when_no_file_exists(self, tmp_path):
        from hermes_prime.agent.identity import AgentIdentity

        identity = AgentIdentity(workspace_root=tmp_path)
        assert identity.name == "Hermes Prime"
        assert identity.persona == "An intelligent AI assistant with access to tools."
        data_path = tmp_path / ".hermes-prime" / "identity.json"
        assert data_path.exists()
        data = json.loads(data_path.read_text())
        assert data["agent_name"] == "Hermes Prime"
        assert data["version"] == 1
        assert "memory_tiers" in data

    def test_loads_existing_identity(self, tmp_path):
        data_path = tmp_path / ".hermes-prime" / "identity.json"
        data_path.parent.mkdir(parents=True)
        data_path.write_text(
            json.dumps({"agent_name": "Custom Agent", "version": 2, "persona": "Custom persona."})
        )

        from hermes_prime.agent.identity import AgentIdentity

        identity = AgentIdentity(workspace_root=tmp_path)
        assert identity.name == "Custom Agent"
        assert identity.persona == "Custom persona."
        assert identity._identity["version"] == 2

    def test_corrupted_json_creates_fresh_identity(self, tmp_path):
        data_path = tmp_path / ".hermes-prime" / "identity.json"
        data_path.parent.mkdir(parents=True)
        data_path.write_text("{corrupted json!!}")

        from hermes_prime.agent.identity import AgentIdentity

        identity = AgentIdentity(workspace_root=tmp_path)
        assert identity.name == "Hermes Prime"
        assert data_path.exists()

    def test_empty_file_creates_fresh_identity(self, tmp_path):
        data_path = tmp_path / ".hermes-prime" / "identity.json"
        data_path.parent.mkdir(parents=True)
        data_path.write_text("")

        from hermes_prime.agent.identity import AgentIdentity

        identity = AgentIdentity(workspace_root=tmp_path)
        assert identity.name == "Hermes Prime"


class TestAgentIdentityUpdate:
    def test_update_modifies_identity(self, tmp_path):
        from hermes_prime.agent.identity import AgentIdentity

        identity = AgentIdentity(workspace_root=tmp_path)
        identity.update(agent_name="New Name", persona="Updated persona.")
        assert identity.name == "New Name"
        assert identity.persona == "Updated persona."

        data_path = tmp_path / ".hermes-prime" / "identity.json"
        data = json.loads(data_path.read_text())
        assert data["agent_name"] == "New Name"
        assert data["persona"] == "Updated persona."

    def test_update_persists_to_disk(self, tmp_path):
        from hermes_prime.agent.identity import AgentIdentity

        identity = AgentIdentity(workspace_root=tmp_path)
        identity.update(agent_name="PersistedName")

        identity2 = AgentIdentity(workspace_root=tmp_path)
        assert identity2.name == "PersistedName"

    def test_update_preserves_existing_keys(self, tmp_path):
        from hermes_prime.agent.identity import AgentIdentity

        identity = AgentIdentity(workspace_root=tmp_path)
        identity.update(version=2)
        identity.update(agent_name="TestName")

        assert identity._identity["version"] == 2
        assert identity._identity["agent_name"] == "TestName"


class TestAgentIdentityBuildSystemPrompt:
    def test_build_system_prompt_includes_name_and_persona(self, tmp_path):
        from hermes_prime.agent.identity import AgentIdentity

        identity = AgentIdentity(workspace_root=tmp_path)
        prompt = identity.build_system_prompt()
        assert "You are Hermes Prime." in prompt
        assert "intelligent AI assistant" in prompt

    def test_build_system_prompt_uses_config_prompt(self, tmp_path):
        from hermes_prime.agent.identity import AgentIdentity

        identity = AgentIdentity(workspace_root=tmp_path)
        prompt = identity.build_system_prompt(config_system_prompt="Custom system prompt.")
        assert "You are Hermes Prime." in prompt
        assert "Custom system prompt." in prompt
        assert "intelligent AI assistant" not in prompt

    def test_build_system_prompt_includes_tools_sentence(self, tmp_path):
        from hermes_prime.agent.identity import AgentIdentity

        identity = AgentIdentity(workspace_root=tmp_path)
        prompt = identity.build_system_prompt()
        assert "use tools to search the web" in prompt

    def test_build_system_prompt_with_memory_store(self, tmp_path):
        from hermes_prime.agent.identity import AgentIdentity

        mock_memory = MagicMock()
        mock_memory.recall.return_value = [
            {"content": "User likes Python programming and data science."},
            {"content": "Previous task involved building a web scraper."},
            {"summary": "User prefers fast iteration."},
        ]
        identity = AgentIdentity(workspace_root=tmp_path, memory_store=mock_memory)
        prompt = identity.build_system_prompt()
        assert "Relevant context from past interactions:" in prompt
        assert "Python programming" in prompt
        assert "web scraper" in prompt
        assert "fast iteration" in prompt
        mock_memory.recall.assert_called_once_with(limit=5, scope="reflective")

    def test_build_system_prompt_memory_truncates_long_content(self, tmp_path):
        from hermes_prime.agent.identity import AgentIdentity

        mock_memory = MagicMock()
        mock_memory.recall.return_value = [
            {"content": "X" * 200},
        ]
        identity = AgentIdentity(workspace_root=tmp_path, memory_store=mock_memory)
        prompt = identity.build_system_prompt()
        assert "..." in prompt
        assert len(prompt) < 500

    def test_build_system_prompt_memory_store_exception_ignored(self, tmp_path):
        from hermes_prime.agent.identity import AgentIdentity

        mock_memory = MagicMock()
        mock_memory.recall.side_effect = Exception("memory unavailable")
        identity = AgentIdentity(workspace_root=tmp_path, memory_store=mock_memory)
        prompt = identity.build_system_prompt()
        assert "You are Hermes Prime." in prompt

    def test_build_system_prompt_without_memory_store(self, tmp_path):
        from hermes_prime.agent.identity import AgentIdentity

        identity = AgentIdentity(workspace_root=tmp_path, memory_store=None)
        prompt = identity.build_system_prompt()
        assert "Relevant context" not in prompt

    def test_build_system_prompt_empty_recall_skips_section(self, tmp_path):
        from hermes_prime.agent.identity import AgentIdentity

        mock_memory = MagicMock()
        mock_memory.recall.return_value = []
        identity = AgentIdentity(workspace_root=tmp_path, memory_store=mock_memory)
        prompt = identity.build_system_prompt()
        assert "Relevant context" not in prompt


class TestAgentIdentityProperties:
    def test_name_property_fallback(self, tmp_path):
        from hermes_prime.agent.identity import AgentIdentity

        identity = AgentIdentity(workspace_root=tmp_path)
        identity._identity.pop("agent_name", None)
        assert identity.name == "Hermes Prime"

    def test_persona_property_fallback(self, tmp_path):
        from hermes_prime.agent.identity import AgentIdentity

        identity = AgentIdentity(workspace_root=tmp_path)
        identity._identity.pop("persona", None)
        assert identity.persona == "An intelligent AI assistant with access to tools."
