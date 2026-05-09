from __future__ import annotations

import asyncio
import time
from collections import defaultdict


class AsyncRateLimiter:
    """Global and per-module cooperative rate limiter."""

    def __init__(self, global_interval: float = 0.0) -> None:
        self.global_interval = global_interval
        self._intervals: dict[str, float] = defaultdict(float)
        self._last_seen: dict[str, float] = defaultdict(float)
        self._lock = asyncio.Lock()

    def configure(self, key: str, interval: float) -> None:
        self._intervals[key] = max(0.0, interval)

    async def wait(self, key: str | None = None) -> None:
        keys = ["__global__"]
        if key:
            keys.append(key)
        async with self._lock:
            now = time.monotonic()
            delay = 0.0
            for item in keys:
                interval = self.global_interval if item == "__global__" else self._intervals[item]
                delay = max(delay, interval - (now - self._last_seen[item]))
            if delay > 0:
                await asyncio.sleep(delay)
                now = time.monotonic()
            for item in keys:
                self._last_seen[item] = now


rate_limiter = AsyncRateLimiter()
