from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RateLimitConfig:
    enabled: bool = False
    requests_per_minute: float = 30.0
    burst_size: int = 5
    concurrency_limit: int = 3


class TokenBucket:
    """Thread-safe token bucket rate limiter."""

    def __init__(self, rate_per_sec: float, burst: int):
        self.rate_per_sec = rate_per_sec
        self.burst = burst
        self.tokens = float(burst)
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(float(self.burst), self.tokens + elapsed * self.rate_per_sec)
        self.last_refill = now

    def acquire(self, tokens: float = 1.0, timeout: Optional[float] = None) -> bool:
        """Acquire tokens. Returns True if acquired, False if timeout."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            with self._lock:
                self._refill()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(0.01)


class RateLimiter:
    """Rate limiter combining token bucket + concurrency limit."""

    def __init__(self, config: RateLimitConfig):
        self.config = config
        rpm = max(1.0, config.requests_per_minute)
        burst = max(1, config.burst_size)
        self._bucket = TokenBucket(rate_per_sec=rpm / 60.0, burst=burst)
        self._semaphore = threading.Semaphore(config.concurrency_limit)
        self._stats = RateLimiterStats()

    def acquire(self, timeout: float = 30.0) -> bool:
        if not self.config.enabled:
            return True
        start = time.monotonic()
        sem_acquired = self._semaphore.acquire(timeout=timeout)
        if not sem_acquired:
            self._stats.total_denied += 1
            return False
        bucket_acquired = self._bucket.acquire(timeout=max(0.1, timeout - (time.monotonic() - start)))
        if not bucket_acquired:
            self._semaphore.release()
            self._stats.total_denied += 1
            return False
        self._stats.total_acquired += 1
        return True

    def release(self) -> None:
        if self.config.enabled:
            self._semaphore.release()

    def __enter__(self) -> "RateLimiter":
        return self

    def __exit__(self, *args: object) -> None:
        self.release()

    @property
    def stats(self) -> RateLimiterStats:
        return self._stats

    def reset_stats(self) -> None:
        self._stats = RateLimiterStats()

    @property
    def is_limited(self) -> bool:
        return self.config.enabled

    def to_dict(self) -> dict:
        return {
            "enabled": self.config.enabled,
            "requests_per_minute": self.config.requests_per_minute,
            "burst_size": self.config.burst_size,
            "concurrency_limit": self.config.concurrency_limit,
            "stats": self._stats.to_dict(),
        }


@dataclass
class RateLimiterStats:
    total_acquired: int = 0
    total_denied: int = 0
    started_at: float = field(default_factory=time.monotonic)

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at

    @property
    def effective_rpm(self) -> float:
        elapsed = self.elapsed_seconds
        if elapsed < 1.0:
            return 0.0
        return (self.total_acquired / elapsed) * 60.0

    def to_dict(self) -> dict:
        return {
            "total_acquired": self.total_acquired,
            "total_denied": self.total_denied,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "effective_rpm": round(self.effective_rpm, 1),
        }
