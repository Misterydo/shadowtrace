from __future__ import annotations

import re

from bs4 import BeautifulSoup

from shadowtrace.core.models import ModuleCapability, ModuleKind, ModulePriority
from shadowtrace.modules.base import BaseExtractor
from shadowtrace.utils.parser import detect_challenge


class TwitterExtractor(BaseExtractor):
    name = "Twitter"
    site_name = "Twitter"
    description = "X/Twitter public profile, reply/timestamp and URL exposure intelligence"
    capabilities = (ModuleCapability.SOCIAL_SCRAPING, ModuleCapability.PLATFORM_ENUMERATION, ModuleCapability.PROFILE_CORRELATION, ModuleCapability.TIMELINE_GENERATION)
    kind = ModuleKind.HYBRID
    priority = ModulePriority.HIGH
    url_patterns = ("twitter.com", "x.com")

    async def normalize(self, parsed: dict[str, object], context: object | None = None) -> dict[str, object]:
        normalized = dict(parsed)
        description = str(normalized.get("description", ""))
        normalized["shared_urls"] = re.findall(r"https?://[^\s)]+", description)
        normalized["mentions"] = re.findall(r"@[\w.]+", description)
        normalized["intelligence_surface"] = ["public_tweets", "replies", "timestamps", "shared_urls", "internal_ids"]
        return normalized

    async def extract_metadata(self, html: str) -> dict[str, str]:
        soup = BeautifulSoup(html, "lxml")
        title = soup.find("title")
        desc = soup.find("meta", attrs={"name": "description"})
        avatar = soup.find("img", src=re.compile("profile_images"))
        return {
            "title": title.text.strip() if title else "",
            "description": desc.get("content", "") if desc else "",
            "avatar_url": avatar.get("src", "") if avatar else "",
        }

    def fingerprint(self, response, text: str) -> bool:
        if response.status != 200 or detect_challenge(text):
            return False
        if "UserUnavailable" in text or "hasn't tweeted" in text:
            return False
        # X serves sparse HTML to unauthenticated users; prefer positive web metadata over brittle text only.
        soup = BeautifulSoup(text, "lxml")
        og_title = soup.find("meta", property="og:title")
        return bool(og_title or ("followers" in text.lower() and "following" in text.lower()))

    def confidence(self, metadata: dict[str, object]) -> int:
        return 60 + (10 if metadata.get("description") else 0)
