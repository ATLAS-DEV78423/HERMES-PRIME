from __future__ import annotations

from typing import Any, Optional

from .client import LLMClient, LLMRequest, LLMResponse
from .rate_limiter import RateLimitConfig, RateLimiter


class RateLimitedClient(LLMClient):
    """Wrapper that enforces rate limits on any LLMClient."""

    def __init__(
        self,
        inner: LLMClient,
        config: Optional[RateLimitConfig] = None,
    ):
        self._inner = inner
        cfg = config or RateLimitConfig()
        self._limiter = RateLimiter(cfg)

    @property
    def limiter(self) -> RateLimiter:
        return self._limiter

    def health_check(self) -> bool:
        return self._inner.health_check()

    def list_models(self) -> list[str]:
        return self._inner.list_models()

    def infer(self, request: LLMRequest) -> LLMResponse:
        if not self._limiter.acquire():
            return LLMResponse(
                model=request.model,
                message_content="",
                finish_reason="rate_limited",
                tokens_used=0,
                latency_ms=0.0,
            )
        try:
            return self._inner.infer(request)
        finally:
            self._limiter.release()

    def infer_stream(self, request: LLMRequest) -> Any:
        if not self._limiter.acquire():
            yield ""
            return
        try:
            yield from self._inner.infer_stream(request)
        finally:
            self._limiter.release()
