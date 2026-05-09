from __future__ import annotations

import re

from bs4 import BeautifulSoup

from shadowtrace.modules.base import BaseExtractor
from shadowtrace.utils.parser import detect_challenge


class TwitterExtractor(BaseExtractor):
    site_name = "Twitter"
    url_patterns = ("twitter.com", "x.com")

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
