from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .client import LLMClient

_ProviderFactory = Callable[[dict[str, Any]], LLMClient | None]


def auto_detect_client(config: dict[str, Any] | None = None) -> LLMClient | None:
    """Try configured provider first, then fall back through available providers.

    Providers tried in order:
      1. Provider specified in config (ollama, vllm, openai, anthropic)
      2. Ollama (localhost:11434)
      3. vLLM (localhost:8000)

    Returns the first working client or None if none available.
    """
    cfg = config or {}
    preferred = cfg.get("provider", "").lower()

    chain: list[_ProviderFactory] = []
    if preferred == "ollama":
        chain = [_ollama, _vllm]
    elif preferred == "vllm":
        chain = [_vllm, _ollama]
    else:
        chain = [_ollama, _vllm]

    for factory in chain:
        client = factory(cfg)
        if client and client.health_check():
            return client
    return None


def _ollama(cfg: dict[str, Any]) -> LLMClient | None:
    try:
        from .ollama_adapter import OllamaClient

        base_url = cfg.get("ollama_url", "http://localhost:11434")
        return OllamaClient(base_url=base_url)
    except Exception:
        return None


def _vllm(cfg: dict[str, Any]) -> LLMClient | None:
    try:
        from .vllm_adapter import VLLMClient

        base_url = cfg.get("vllm_url", "http://localhost:8000")
        return VLLMClient(base_url=base_url)
    except Exception:
        return None


def get_model_from_config(config: dict[str, Any] | None = None) -> str:
    cfg = config or {}
    return cfg.get("model", "mistral")


def get_system_prompt_from_config(config: dict[str, Any] | None = None) -> str:
    cfg = config or {}
    return cfg.get(
        "system_prompt",
        "You are Hermes Prime, an intelligent AI assistant with access to tools.",
    )
