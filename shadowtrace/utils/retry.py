from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


def backoff_delay(attempt: int, *, base: float = 1.0, cap: float = 30.0) -> float:
    return min(cap, (2**attempt) * base) + random.uniform(0, 0.8)


async def retry_async(factory: Callable[[int], Awaitable[T]], retries: int) -> T:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return await factory(attempt)
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                break
            await asyncio.sleep(backoff_delay(attempt))
    assert last_error is not None
    raise last_error
