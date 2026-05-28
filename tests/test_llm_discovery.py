from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestAutoDetectClient:
    def test_no_config_tries_ollama_first(self):
        mock_ollama = MagicMock()
        mock_ollama.health_check.return_value = True

        with patch(
            "hermes_prime.llm.discovery._ollama", return_value=mock_ollama
        ) as mock_ollama_factory:
            with patch("hermes_prime.llm.discovery._vllm") as mock_vllm_factory:
                from hermes_prime.llm.discovery import auto_detect_client

                result = auto_detect_client(None)
                assert result is mock_ollama
                mock_ollama_factory.assert_called_once()
                mock_vllm_factory.assert_not_called()

    def test_preferred_provider_ollama(self):
        mock_ollama = MagicMock()
        mock_ollama.health_check.return_value = True

        with patch(
            "hermes_prime.llm.discovery._ollama", return_value=mock_ollama
        ) as mock_ollama_factory:
            with patch("hermes_prime.llm.discovery._vllm") as mock_vllm_factory:
                from hermes_prime.llm.discovery import auto_detect_client

                result = auto_detect_client({"provider": "ollama"})
                assert result is mock_ollama
                mock_ollama_factory.assert_called_once()
                mock_vllm_factory.assert_not_called()

    def test_preferred_provider_vllm(self):
        mock_vllm = MagicMock()
        mock_vllm.health_check.return_value = True

        with patch("hermes_prime.llm.discovery._ollama") as mock_ollama_factory:
            with patch(
                "hermes_prime.llm.discovery._vllm", return_value=mock_vllm
            ) as mock_vllm_factory:
                from hermes_prime.llm.discovery import auto_detect_client

                result = auto_detect_client({"provider": "vllm"})
                assert result is mock_vllm
                mock_vllm_factory.assert_called_once()
                mock_ollama_factory.assert_not_called()

    def test_unknown_provider_falls_to_default_order(self):
        mock_ollama = MagicMock()
        mock_ollama.health_check.return_value = True

        with patch(
            "hermes_prime.llm.discovery._ollama", return_value=mock_ollama
        ) as mock_ollama_factory:
            with patch("hermes_prime.llm.discovery._vllm") as mock_vllm_factory:
                from hermes_prime.llm.discovery import auto_detect_client

                result = auto_detect_client({"provider": "openai"})
                assert result is mock_ollama
                mock_ollama_factory.assert_called_once()
                mock_vllm_factory.assert_not_called()

    def test_preferred_provider_fails_falls_through(self):
        mock_ollama = MagicMock()
        mock_ollama.health_check.return_value = False
        mock_vllm = MagicMock()
        mock_vllm.health_check.return_value = True

        with patch(
            "hermes_prime.llm.discovery._ollama", return_value=mock_ollama
        ) as mock_ollama_factory:
            with patch(
                "hermes_prime.llm.discovery._vllm", return_value=mock_vllm
            ) as mock_vllm_factory:
                from hermes_prime.llm.discovery import auto_detect_client

                result = auto_detect_client({"provider": "ollama"})
                assert result is mock_vllm
                mock_ollama_factory.assert_called_once()
                mock_vllm_factory.assert_called_once()

    def test_all_providers_fail_returns_none(self):
        mock_ollama = MagicMock()
        mock_ollama.health_check.return_value = False
        mock_vllm = MagicMock()
        mock_vllm.health_check.return_value = False

        with patch(
            "hermes_prime.llm.discovery._ollama", return_value=mock_ollama
        ):
            with patch(
                "hermes_prime.llm.discovery._vllm", return_value=mock_vllm
            ):
                from hermes_prime.llm.discovery import auto_detect_client

                result = auto_detect_client(None)
                assert result is None

    def test_config_provider_case_insensitive(self):
        mock_ollama = MagicMock()
        mock_ollama.health_check.return_value = True
        mock_vllm = MagicMock()
        mock_vllm.health_check.return_value = True

        with patch(
            "hermes_prime.llm.discovery._ollama", return_value=mock_ollama
        ):
            with patch(
                "hermes_prime.llm.discovery._vllm", return_value=mock_vllm
            ):
                from hermes_prime.llm.discovery import auto_detect_client

                result_upper = auto_detect_client({"provider": "OLLAMA"})
                assert result_upper is mock_ollama

                result_mixed = auto_detect_client({"provider": "VLLM"})
                assert result_mixed is mock_vllm


class TestAutoDetectClientFactories:
    def test_ollama_factory_import_error_returns_none(self):
        with patch(
            "hermes_prime.llm.discovery._ollama",
            return_value=None,
        ):
            from hermes_prime.llm.discovery import _ollama

            result = _ollama({})
            assert result is None

    def test_vllm_factory_returns_client(self):
        with patch(
            "hermes_prime.llm.discovery._vllm",
            return_value=MagicMock(),
        ):
            from hermes_prime.llm.discovery import _vllm

            result = _vllm({"vllm_url": "http://custom:8080"})
            assert result is not None


class TestGetModelFromConfig:
    def test_default_model(self):
        from hermes_prime.llm.discovery import get_model_from_config

        assert get_model_from_config(None) == "mistral"
        assert get_model_from_config({}) == "mistral"

    def test_custom_model(self):
        from hermes_prime.llm.discovery import get_model_from_config

        assert get_model_from_config({"model": "llama3"}) == "llama3"

    def test_model_not_overridden_by_other_keys(self):
        from hermes_prime.llm.discovery import get_model_from_config

        assert (
            get_model_from_config({"provider": "ollama", "temperature": 0.5})
            == "mistral"
        )


class TestGetSystemPromptFromConfig:
    def test_default_system_prompt(self):
        from hermes_prime.llm.discovery import get_system_prompt_from_config

        prompt = get_system_prompt_from_config(None)
        assert "Hermes Prime" in prompt
        assert "intelligent AI assistant" in prompt

    def test_custom_system_prompt(self):
        from hermes_prime.llm.discovery import get_system_prompt_from_config

        custom = "You are a coding assistant."
        assert (
            get_system_prompt_from_config({"system_prompt": custom})
            == custom
        )

    def test_default_prompt_unchanged_by_empty_config(self):
        from hermes_prime.llm.discovery import get_system_prompt_from_config

        prompt = get_system_prompt_from_config({})
        assert "Hermes Prime" in prompt
