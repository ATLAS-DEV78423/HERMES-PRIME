from __future__ import annotations

import json
import time
from collections.abc import Generator

import requests

from .client import LLMClient, LLMRequest, LLMResponse


class VLLMClient(LLMClient):
    """vLLM OpenAI-compatible adapter."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def health_check(self) -> bool:
        """Check vLLM endpoint connectivity."""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """List available models via /v1/models."""
        try:
            response = self.session.get(f"{self.base_url}/v1/models", timeout=10)
            if response.status_code != 200:
                return []
            data = response.json()
            return [model["id"] for model in data.get("data", [])]
        except Exception:
            return []

    def infer(self, request: LLMRequest) -> LLMResponse:
        """Execute inference via OpenAI-compatible /v1/chat/completions."""
        start_time = time.time()

        payload = {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "top_p": request.top_p,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        try:
            response = self.session.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                timeout=120,
            )
            if response.status_code != 200:
                return LLMResponse(
                    model=request.model,
                    message_content="",
                    finish_reason="error",
                    tokens_used=0,
                    latency_ms=(time.time() - start_time) * 1000,
                )

            data = response.json()
            choice = data.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "")
            usage = data.get("usage", {})
            tokens = usage.get("completion_tokens", 0)

            return LLMResponse(
                model=request.model,
                message_content=content,
                finish_reason=choice.get("finish_reason", "stop"),
                tokens_used=tokens,
                latency_ms=(time.time() - start_time) * 1000,
            )
        except Exception:
            return LLMResponse(
                model=request.model,
                message_content="",
                finish_reason="error",
                tokens_used=0,
                latency_ms=(time.time() - start_time) * 1000,
            )

    def infer_stream(self, request: LLMRequest) -> Generator[str, None, None]:
        """Stream tokens from vLLM via /v1/chat/completions with stream=True."""
        payload = {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": True,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        with self.session.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            stream=True,
            timeout=120,
        ) as response:
            for line in response.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8") if isinstance(line, bytes) else line
                if not decoded.startswith("data: "):
                    continue
                data_str = decoded.removeprefix("data: ")
                if data_str.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    token = delta.get("content", "")
                    if token:
                        yield token
                except json.JSONDecodeError:
                    continue
