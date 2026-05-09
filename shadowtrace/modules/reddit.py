from __future__ import annotations

import re

from shadowtrace.core.models import ModuleCapability, ModuleKind, ModulePriority
from shadowtrace.modules.base import BaseExtractor
from shadowtrace.utils.parser import meta_map, tolerant_soup


class RedditExtractor(BaseExtractor):
    name = "Reddit"
    site_name = "Reddit"
    description = "Reddit public activity, subreddit and behavior-pattern intelligence"
    capabilities = (ModuleCapability.SOCIAL_SCRAPING, ModuleCapability.PLATFORM_ENUMERATION, ModuleCapability.PROFILE_CORRELATION, ModuleCapability.TIMELINE_GENERATION)
    kind = ModuleKind.HYBRID
    priority = ModulePriority.HIGH
    url_patterns = ("reddit.com",)
    positive_patterns = ("profilesidebar", "karma", "reddit.com/user", "overview", "comments")
    negative_patterns = BaseExtractor.negative_patterns + ("nobody on reddit goes by that name",)

    async def normalize(self, parsed: dict[str, object], context: object | None = None) -> dict[str, object]:
        normalized = dict(parsed)
        bio = str(normalized.get("bio", ""))
        normalized["mentioned_subreddits"] = re.findall(r"r/[A-Za-z0-9_]+", bio)
        normalized["intelligence_surface"] = ["subreddits", "comments", "karma", "language", "temporal_activity"]
        return normalized

    async def extract_metadata(self, html: str) -> dict[str, str]:
        soup = tolerant_soup(html)
        karma = soup.find("span", class_=re.compile("karma"))
        bio = soup.find("div", class_="bio")
        avatar = soup.find("img", class_="ProfileSidebar__avatar")
        metas = meta_map(html)
        return {
            "karma": karma.text.strip() if karma else "",
            "bio": bio.text.strip() if bio else metas.get("og:description", ""),
            "avatar_url": avatar.get("src", "") if avatar else metas.get("og:image", ""),
        }

    def fingerprint(self, response, text: str) -> bool:
        return bool(self.heuristic_detect({"status": response.status, "html": text}).get("exists"))
