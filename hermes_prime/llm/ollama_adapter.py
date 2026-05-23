from __future__ import annotations

import json
import time
from typing import Optional

import requests

from .client import LLMClient, LLMRequest, LLMResponse


class OllamaClient(LLMClient):
    """Ollama HTTP adapter."""

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def health_check(self) -> bool:
        """Check Ollama connectivity."""
        try:
            response = self.session.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """List available models via /api/tags."""
        try:
            response = self.session.get(f"{self.base_url}/api/tags", timeout=10)
            if response.status_code != 200:
                return []
            data = response.json()
            return [model["name"] for model in data.get("models", [])]
        except Exception:
            return []

    def infer(self, request: LLMRequest) -> LLMResponse:
        """Execute inference via /api/generate or /api/chat."""
        start_time = time.time()
        
        # Use /api/chat for multi-turn conversations
        payload = {
            "model": request.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "stream": False,
        }
        if request.max_tokens is not None:
            payload["num_predict"] = request.max_tokens

        try:
            response = self.session.post(
                f"{self.base_url}/api/chat",
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
            message = data.get("message", {})
            content = message.get("content", "")
            tokens = data.get("eval_count", 0)
            
            return LLMResponse(
                model=request.model,
                message_content=content,
                finish_reason="stop",
                tokens_used=tokens,
                latency_ms=(time.time() - start_time) * 1000,
            )
        except Exception as e:
            return LLMResponse(
                model=request.model,
                message_content="",
                finish_reason="error",
                tokens_used=0,
                latency_ms=(time.time() - start_time) * 1000,
            )
