from __future__ import annotations

import re

from shadowtrace.core.models import ModuleCapability, ModuleKind, ModulePriority
from shadowtrace.modules.base import BaseExtractor
from shadowtrace.utils.parser import detect_lang, iter_json_blobs, meta_map, tolerant_soup


class InstagramExtractor(BaseExtractor):
    name = "Instagram"
    site_name = "Instagram"
    description = "Instagram public profile and indirect exposure intelligence"
    capabilities = (ModuleCapability.SOCIAL_SCRAPING, ModuleCapability.PLATFORM_ENUMERATION, ModuleCapability.PROFILE_CORRELATION, ModuleCapability.METADATA_EXTRACTION)
    kind = ModuleKind.HYBRID
    priority = ModulePriority.HIGH
    url_patterns = ("instagram.com",)
    positive_patterns = ("profilepage_", "edge_followed_by", "followers", "following", "og:description")
    negative_patterns = BaseExtractor.negative_patterns + ("sorry, this page isn't available", "page isn't available")

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
        soup = tolerant_soup(html)
        user_data: dict = {}
        for data in iter_json_blobs(html):
            try:
                if isinstance(data, dict) and "entry_data" in data and "ProfilePage" in data["entry_data"]:
                    user_data = data["entry_data"]["ProfilePage"][0]["graphql"]["user"]
                    break
                if isinstance(data, dict) and data.get("@type") == "Person":
                    user_data = data
                    break
            except (KeyError, TypeError, IndexError):
                continue
        if user_data:
            metadata = {
                "full_name": user_data.get("full_name", ""),
                "bio": user_data.get("biography", "") or user_data.get("description", ""),
                "followers": user_data.get("edge_followed_by", {}).get("count", 0),
                "avatar_url": user_data.get("profile_pic_url", user_data.get("image", "")),
            }
            metadata["lang_bio"] = detect_lang(str(metadata.get("bio", "")))
            return metadata
        metas = meta_map(html)
        metadata = {"bio": metas.get("og:description", "") or metas.get("description", ""), "avatar_url": metas.get("og:image", "")}
        metadata["lang_bio"] = detect_lang(str(metadata["bio"]))
        return metadata

    def fingerprint(self, response, text: str) -> bool:
        return bool(self.heuristic_detect({"status": response.status, "html": text}).get("exists"))

    def confidence(self, metadata: dict[str, object]) -> int:
        if metadata.get("confidence_score"):
            return int(metadata["confidence_score"])
        detection = metadata.get("_detection") if isinstance(metadata.get("_detection"), dict) else {}
        base = int(detection.get("confidence") or 40)
        return min(99, base + (10 if metadata.get("bio") else 0))
