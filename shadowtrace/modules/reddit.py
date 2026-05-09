from __future__ import annotations

import re

from bs4 import BeautifulSoup

from shadowtrace.modules.base import BaseExtractor
from shadowtrace.utils.parser import detect_challenge


class RedditExtractor(BaseExtractor):
    site_name = "Reddit"
    url_patterns = ("reddit.com",)

    async def extract_metadata(self, html: str) -> dict[str, str]:
        soup = BeautifulSoup(html, "lxml")
        karma = soup.find("span", class_=re.compile("karma"))
        bio = soup.find("div", class_="bio")
        avatar = soup.find("img", class_="ProfileSidebar__avatar")
        return {
            "karma": karma.text.strip() if karma else "",
            "bio": bio.text.strip() if bio else "",
            "avatar_url": avatar.get("src", "") if avatar else "",
        }

    def fingerprint(self, response, text: str) -> bool:
        if response.status != 200 or detect_challenge(text):
            return False
        soup = BeautifulSoup(text, "lxml")
        return bool(soup.find("div", class_="ProfileSidebar") or "reddit.com/user" in text)
