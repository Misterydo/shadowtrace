from __future__ import annotations

import re

from shadowtrace.core.models import ModuleCapability, ModuleKind, ModulePriority
from shadowtrace.modules.base import BaseExtractor
from shadowtrace.utils.parser import meta_map, tolerant_soup


class TwitterExtractor(BaseExtractor):
    name = "Twitter"
    site_name = "Twitter"
    description = "X/Twitter public profile, reply/timestamp and URL exposure intelligence"
    capabilities = (ModuleCapability.SOCIAL_SCRAPING, ModuleCapability.PLATFORM_ENUMERATION, ModuleCapability.PROFILE_CORRELATION, ModuleCapability.TIMELINE_GENERATION)
    kind = ModuleKind.HYBRID
    priority = ModulePriority.HIGH
    url_patterns = ("twitter.com", "x.com")
    positive_patterns = ("followers", "following", "profile_images", "og:title", "twitter:description")
    negative_patterns = BaseExtractor.negative_patterns + ("this account doesn’t exist", "account suspended")

    async def normalize(self, parsed: dict[str, object], context: object | None = None) -> dict[str, object]:
        normalized = dict(parsed)
        description = str(normalized.get("description", ""))
        normalized["shared_urls"] = re.findall(r"https?://[^\s)]+", description)
        normalized["mentions"] = re.findall(r"@[\w.]+", description)
        normalized["intelligence_surface"] = ["public_tweets", "replies", "timestamps", "shared_urls", "internal_ids"]
        return normalized

    async def extract_metadata(self, html: str) -> dict[str, str]:
        soup = tolerant_soup(html)
        metas = meta_map(html)
        title = soup.find("title")
        avatar = soup.find("img", src=re.compile("profile_images"))
        return {
            "title": metas.get("og:title", "") or (title.text.strip() if title else ""),
            "description": metas.get("description", "") or metas.get("og:description", "") or metas.get("twitter:description", ""),
            "avatar_url": avatar.get("src", "") if avatar else metas.get("og:image", ""),
        }

    def fingerprint(self, response, text: str) -> bool:
        return bool(self.heuristic_detect({"status": response.status, "html": text}).get("exists"))

    def confidence(self, metadata: dict[str, object]) -> int:
        if metadata.get("confidence_score"):
            return int(metadata["confidence_score"])
        detection = metadata.get("_detection") if isinstance(metadata.get("_detection"), dict) else {}
        return min(99, int(detection.get("confidence") or 60) + (10 if metadata.get("description") else 0))
