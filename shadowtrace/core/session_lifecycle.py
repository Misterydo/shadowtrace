from __future__ import annotations

from shadowtrace.core.cache import cache
from shadowtrace.core.session import session_manager


async def shutdown() -> None:
    await session_manager.close()
    await cache.close()
