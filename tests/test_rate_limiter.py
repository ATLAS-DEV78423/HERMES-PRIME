from __future__ import annotations

import pytest
import time
from unittest.mock import MagicMock, patch

from hermes_prime.llm.client import LLMRequest, LLMResponse
from hermes_prime.llm.rate_limiter import RateLimitConfig, RateLimiter, RateLimiterStats, TokenBucket


class TestTokenBucket:
    def test_initial_tokens_equal_burst(self):
        bucket = TokenBucket(rate_per_sec=10.0, burst=5)
        assert bucket.tokens == 5.0

    def test_acquire_consumes_tokens(self):
        bucket = TokenBucket(rate_per_sec=100.0, burst=10)
        assert bucket.acquire(tokens=3.0)
        assert bucket.tokens == 7.0

    def test_acquire_blocks_when_empty(self):
        bucket = TokenBucket(rate_per_sec=0.1, burst=1)
        bucket.tokens = 0.0
        assert not bucket.acquire(timeout=0.05)

    def test_acquire_succeeds_after_refill(self):
        bucket = TokenBucket(rate_per_sec=100.0, burst=10)
        bucket.tokens = 0.0
        bucket.last_refill = time.monotonic() - 1.0
        assert bucket.acquire(timeout=0.1)
        assert bucket.tokens > 0

    def test_concurrent_safety(self):
        import threading

        bucket = TokenBucket(rate_per_sec=1000.0, burst=1000)
        errors = []

        def hammer():
            for _ in range(100):
                if not bucket.acquire(timeout=1.0):
                    errors.append("failed")

        threads = [threading.Thread(target=hammer) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


class TestRateLimiterStats:
    def test_initial_zero(self):
        stats = RateLimiterStats()
        assert stats.total_acquired == 0
        assert stats.total_denied == 0

    def test_effective_rpm(self):
        stats = RateLimiterStats(total_acquired=10, started_at=time.monotonic() - 60)
        assert stats.effective_rpm == pytest.approx(10.0, abs=0.01)

    def test_effective_rpm_before_one_second(self):
        stats = RateLimiterStats(total_acquired=1)
        assert stats.effective_rpm == 0.0

    def test_to_dict(self):
        stats = RateLimiterStats(total_acquired=5, total_denied=2)
        d = stats.to_dict()
        assert d["total_acquired"] == 5
        assert d["total_denied"] == 2


class TestRateLimiter:
    def test_disabled_bypasses_limiting(self):
        config = RateLimitConfig(enabled=False)
        limiter = RateLimiter(config)
        with limiter:
            assert limiter.acquire()

    def test_enabled_acquire_success(self):
        config = RateLimitConfig(enabled=True, requests_per_minute=1000.0, burst_size=100, concurrency_limit=10)
        limiter = RateLimiter(config)
        assert limiter.acquire()
        limiter.release()

    def test_is_limited_property(self):
        enabled = RateLimiter(RateLimitConfig(enabled=True))
        disabled = RateLimiter(RateLimitConfig(enabled=False))
        assert enabled.is_limited
        assert not disabled.is_limited

    def test_reset_stats(self):
        limiter = RateLimiter(RateLimitConfig(enabled=True, requests_per_minute=1000.0, burst_size=100, concurrency_limit=10))
        limiter._stats.total_acquired = 42
        limiter.reset_stats()
        assert limiter.stats.total_acquired == 0

    def test_to_dict(self):
        config = RateLimitConfig(enabled=True, requests_per_minute=30.0, burst_size=5, concurrency_limit=3)
        limiter = RateLimiter(config)
        d = limiter.to_dict()
        assert d["enabled"]
        assert d["requests_per_minute"] == 30.0
        assert d["burst_size"] == 5
        assert d["concurrency_limit"] == 3
        assert "stats" in d


class TestRateLimitedClient:
    def test_health_check_delegates(self):
        from hermes_prime.llm.rate_limited_client import RateLimitedClient

        inner = MagicMock()
        inner.health_check.return_value = True
        client = RateLimitedClient(inner)
        assert client.health_check()
        inner.health_check.assert_called_once()

    def test_list_models_delegates(self):
        from hermes_prime.llm.rate_limited_client import RateLimitedClient

        inner = MagicMock()
        inner.list_models.return_value = ["model-a", "model-b"]
        client = RateLimitedClient(inner)
        assert client.list_models() == ["model-a", "model-b"]

    def test_infer_passes_through_when_limited(self):
        from hermes_prime.llm.rate_limited_client import RateLimitedClient

        inner = MagicMock()
        inner.infer.return_value = LLMResponse(
            model="test",
            message_content="ok",
            finish_reason="stop",
            tokens_used=10,
            latency_ms=5.0,
        )
        config = RateLimitConfig(enabled=False)
        client = RateLimitedClient(inner, config=config)
        request = LLMRequest(model="test", messages=[{"role": "user", "content": "hi"}])
        resp = client.infer(request)
        assert resp.message_content == "ok"
        inner.infer.assert_called_once_with(request)

    def test_infer_returns_rate_limited_when_throttled(self):
        from hermes_prime.llm.rate_limited_client import RateLimitedClient

        inner = MagicMock()
        config = RateLimitConfig(enabled=True, requests_per_minute=0.0, burst_size=1, concurrency_limit=0)
        client = RateLimitedClient(inner, config=config)
        request = LLMRequest(model="test", messages=[{"role": "user", "content": "hi"}])
        resp = client.infer(request)
        assert resp.finish_reason == "rate_limited"
        inner.infer.assert_not_called()

    def test_limiter_property(self):
        from hermes_prime.llm.rate_limited_client import RateLimitedClient

        inner = MagicMock()
        client = RateLimitedClient(inner)
        assert client.limiter is not None
        assert isinstance(client.limiter, RateLimiter)

    def test_infer_stream_when_throttled(self):
        from hermes_prime.llm.rate_limited_client import RateLimitedClient

        inner = MagicMock()
        config = RateLimitConfig(enabled=True, requests_per_minute=60.0, burst_size=1, concurrency_limit=1)
        client = RateLimitedClient(inner, config=config)
        client._limiter.acquire = MagicMock(return_value=False)  # type: ignore[assignment]
        request = LLMRequest(model="test", messages=[{"role": "user", "content": "hi"}])
        gen = client.infer_stream(request)
        chunks = list(gen)
        assert chunks == [""]
        inner.infer_stream.assert_not_called()
