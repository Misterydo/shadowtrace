from __future__ import annotations

import asyncio
import random
from types import TracebackType
from typing import Any

import aiohttp
from aiohttp_socks import ProxyConnector

from shadowtrace.core.config import CONFIG, ShadowTraceConfig
from shadowtrace.utils.retry import backoff_delay


class HTTPSessionManager:
    def __init__(self, config: ShadowTraceConfig = CONFIG) -> None:
        self.config = config
        self._session: aiohttp.ClientSession | None = None
        self._semaphore: object | None = None

    async def get(self) -> aiohttp.ClientSession:
        if self._session and not self._session.closed:
            return self._session
        timeout = aiohttp.ClientTimeout(total=self.config.timeout, connect=min(10, self.config.timeout), sock_read=self.config.timeout)
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


_ACCEPT_LANGUAGE = [
    "en-US,en;q=0.9",
    "en-US,en;q=0.9,pt-BR;q=0.8",
    "en-GB,en;q=0.9,en-US;q=0.8",
]
_SEC_FETCH_SITE = ["none", "same-origin", "cross-site"]


def random_stealth_headers(config: ShadowTraceConfig = CONFIG) -> dict[str, str]:
    """Return randomized browser-like headers for resilient public OSINT requests."""

    return {
        "User-Agent": random.choice(config.user_agents),
        "Accept": random.choice(config.accept_headers),
        "Accept-Language": random.choice(_ACCEPT_LANGUAGE),
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": random.choice(config.referers),
        "Sec-CH-UA": random.choice(config.sec_ch_ua_headers),
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": random.choice(['"Windows"', '"macOS"', '"Linux"']),
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": random.choice(_SEC_FETCH_SITE),
        "Sec-Fetch-User": "?1",
        "DNT": str(random.choice([0, 1])),
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


async def fetch_text(
    session: aiohttp.ClientSession,
    url: str,
    config: ShadowTraceConfig = CONFIG,
    *,
    attempts: int | None = None,
) -> dict[str, Any]:
    """Fetch a URL with retries, redirects and tolerant response decoding."""

    max_attempts = config.max_retries + 1 if attempts is None else max(1, attempts)
    last_error: str | None = None
    for attempt in range(max_attempts):
        try:
            async with session.get(
                url,
                headers=random_stealth_headers(config),
                allow_redirects=True,
            ) as response:
                body = await response.content.read(config.max_response_bytes)
                charset = response.charset or "utf-8"
                html = body.decode(charset, errors="ignore")
                return {
                    "url": url,
                    "final_url": str(response.url),
                    "status": response.status,
                    "reason": response.reason,
                    "charset": response.charset,
                    "headers": dict(response.headers),
                    "history": [str(item.url) for item in response.history],
                    "html": html,
                    "content_length": len(body),
                    "error": None,
                }
        except (asyncio.TimeoutError, aiohttp.ClientError, UnicodeError) as exc:
            last_error = "timeout" if isinstance(exc, asyncio.TimeoutError) else str(exc)
            if attempt < max_attempts - 1:
                await asyncio.sleep(backoff_delay(attempt))
    return {"url": url, "final_url": url, "status": 0, "html": "", "content_length": 0, "history": [], "error": last_error}


session_manager = HTTPSessionManager()
