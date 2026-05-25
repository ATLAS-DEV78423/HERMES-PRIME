from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from collections.abc import Generator
from typing import Optional


@dataclass
class LLMRequest:
    """Structured request to an LLM."""
    model: str
    messages: list[dict[str, str]]  # [{"role": "user|system", "content": "..."}, ...]
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 0.95
    stream: bool = False


@dataclass
class LLMResponse:
    """Structured response from an LLM."""
    model: str
    message_content: str
    finish_reason: str  # "stop", "length", "error", etc.
    tokens_used: int
    latency_ms: float


class LLMClient(ABC):
    """Abstract base class for LLM provider adapters."""

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the LLM provider is reachable and operational."""
        pass

    @abstractmethod
    def list_models(self) -> list[str]:
        """List available models."""
        pass

    @abstractmethod
    def infer(self, request: LLMRequest) -> LLMResponse:
        """Execute inference request and return structured response."""
        pass
