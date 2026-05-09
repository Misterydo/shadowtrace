from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable
from typing import TypeVar

from shadowtrace.core.config import CONFIG, ShadowTraceConfig

T = TypeVar("T")


class AsyncManager:
    def __init__(self, config: ShadowTraceConfig = CONFIG) -> None:
        self.config = config
        self._semaphore = asyncio.Semaphore(config.threads)

    def resize(self, threads: int) -> None:
        self.config.threads = threads
        self._semaphore = asyncio.Semaphore(threads)

    async def gather_limited(self, awaitables: list[Awaitable[T]]) -> list[T]:
        async def runner(awaitable: Awaitable[T]) -> T:
            async with self._semaphore:
                if self.config.stealth:
                    low, high = self.config.sem_delay_ms
                    await asyncio.sleep(random.uniform(low / 1000, high / 1000))
                return await awaitable
        return await asyncio.gather(*(runner(item) for item in awaitables))


async_manager = AsyncManager()
