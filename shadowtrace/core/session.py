from __future__ import annotations

import random
from types import TracebackType

import aiohttp
from aiohttp_socks import ProxyConnector

from shadowtrace.core.config import CONFIG, ShadowTraceConfig


class HTTPSessionManager:
    def __init__(self, config: ShadowTraceConfig = CONFIG) -> None:
        self.config = config
        self._session: aiohttp.ClientSession | None = None
        self._semaphore: object | None = None

    async def get(self) -> aiohttp.ClientSession:
        if self._session and not self._session.closed:
            return self._session
        timeout = aiohttp.ClientTimeout(total=self.config.timeout, connect=min(10, self.config.timeout))
        proxy = self.config.proxy()
        connector: aiohttp.BaseConnector | None = None
        if proxy and proxy.startswith("socks"):
            connector = ProxyConnector.from_url(proxy)
        elif proxy:
            connector = aiohttp.TCPConnector(limit_per_host=max(1, self.config.threads))
        self._session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            max_line_size=16_384,
            max_field_size=16_384,
        )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def __aenter__(self) -> "HTTPSessionManager":
        await self.get()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()


def random_stealth_headers(config: ShadowTraceConfig = CONFIG) -> dict[str, str]:
    return {
        "User-Agent": random.choice(config.user_agents),
        "Accept": random.choice(config.accept_headers),
        "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": random.choice(config.referers),
        "Sec-CH-UA": random.choice(config.sec_ch_ua_headers),
        "DNT": str(random.choice([0, 1])),
        "Upgrade-Insecure-Requests": "1",
    }


session_manager = HTTPSessionManager()
