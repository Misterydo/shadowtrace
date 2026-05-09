from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from shadowtrace.core.models import ModuleCapability, ModuleKind, ModulePriority
from shadowtrace.modules.base import BaseExtractor
from shadowtrace.utils.parser import detect_challenge, detect_lang


class InstagramExtractor(BaseExtractor):
    name = "Instagram"
    site_name = "Instagram"
    description = "Instagram public profile and indirect exposure intelligence"
    capabilities = (ModuleCapability.SOCIAL_SCRAPING, ModuleCapability.PLATFORM_ENUMERATION, ModuleCapability.PROFILE_CORRELATION, ModuleCapability.METADATA_EXTRACTION)
    kind = ModuleKind.HYBRID
    priority = ModulePriority.HIGH
    url_patterns = ("instagram.com",)

    def build_dorks(self, username: str) -> list[str]:
        return [
            f'site:instagram.com "{username}"',
            f'site:instagram.com "{username}" "/p/"',
            f'site:instagram.com "{username}" "@"',
            f'site:instagram.com "{username}" "bio"',
        ]

    async def normalize(self, parsed: dict[str, object], context: object | None = None) -> dict[str, object]:
        normalized = dict(parsed)
        bio = str(normalized.get("bio", ""))
        normalized["external_links"] = re.findall(r"https?://[^\s)]+", bio)
        normalized["hashtags"] = re.findall(r"#[\w.]+", bio)
        normalized["mentions"] = re.findall(r"@[\w.]+", bio)
        normalized["intelligence_surface"] = ["bio", "external_links", "hashtags", "mentions", "indexed_comments"]
        return normalized

    async def extract_metadata(self, html: str) -> dict[str, object]:
        soup = BeautifulSoup(html, "lxml")
        hydration: str | None = None
        for script in soup.find_all("script"):
            if script.string and "profilePage_" in script.string:
                match = re.search(r"window\._sharedData\s*=\s*({.*});", script.string)
                if match:
                    hydration = match.group(1)
                    break
            if script.string and "application/ld+json" in script.get("type", ""):
                hydration = script.string
                break
        user_data: dict = {}
        if hydration:
            try:
                data = json.loads(hydration)
                if "entry_data" in data and "ProfilePage" in data["entry_data"]:
                    user_data = data["entry_data"]["ProfilePage"][0]["graphql"]["user"]
                elif data.get("@type") == "Person":
                    user_data = data
            except (KeyError, TypeError, json.JSONDecodeError):
                user_data = {}
        if user_data:
            metadata = {
                "full_name": user_data.get("full_name", ""),
                "bio": user_data.get("biography", "") or user_data.get("description", ""),
                "followers": user_data.get("edge_followed_by", {}).get("count", 0),
                "avatar_url": user_data.get("profile_pic_url", user_data.get("image", "")),
            }
            metadata["lang_bio"] = detect_lang(str(metadata.get("bio", "")))
            return metadata
        meta_tag = soup.find("meta", property="og:description")
        metadata = {"bio": meta_tag.get("content", "") if meta_tag else ""}
        metadata["lang_bio"] = detect_lang(str(metadata["bio"]))
        return metadata

    def fingerprint(self, response, text: str) -> bool:
        if response.status not in (200, 301, 302) or detect_challenge(text):
            return False
        soup = BeautifulSoup(text, "lxml")
        return '"profilePage_' in text or '"graphql": {' in text or bool(soup.find("meta", {"property": "og:title"}))

    def confidence(self, metadata: dict[str, object]) -> int:
        return 70 if metadata.get("bio") else 40
