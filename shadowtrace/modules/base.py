from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import aiohttp

from shadowtrace.utils.parser import detect_challenge


class BaseExtractor(ABC):
    site_name: str = ""
    url_patterns: tuple[str, ...] = ()

    @classmethod
    def is_url_match(cls, url: str) -> bool:
        return any(pattern in url for pattern in cls.url_patterns)

    @abstractmethod
    async def extract_metadata(self, html: str) -> dict[str, Any]:
        raise NotImplementedError

    def confidence(self, metadata: dict[str, Any]) -> int:
        return 80

    def fingerprint(self, response: aiohttp.ClientResponse, text: str) -> bool:
        return response.status == 200 and len(text) > 100 and not detect_challenge(text)
