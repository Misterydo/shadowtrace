from __future__ import annotations

import re

from shadowtrace.core.models import ModuleCapability, ModuleKind, ModulePriority
from shadowtrace.modules.base import BaseExtractor
from shadowtrace.utils.parser import detect_lang, meta_map, tolerant_soup


class GitHubExtractor(BaseExtractor):
    name = "GitHub"
    site_name = "GitHub"
    description = "GitHub developer, repository, organization and commit-fingerprint intelligence"
    capabilities = (ModuleCapability.GITHUB_INTELLIGENCE, ModuleCapability.PLATFORM_ENUMERATION, ModuleCapability.PROFILE_CORRELATION, ModuleCapability.METADATA_EXTRACTION)
    kind = ModuleKind.HYBRID
    priority = ModulePriority.HIGH
    url_patterns = ("github.com",)
    positive_patterns = ("contribution", "repositories", "followers", "following", "p-nickname", "avatar-user")

    async def normalize(self, parsed: dict[str, object], context: object | None = None) -> dict[str, object]:
        normalized = dict(parsed)
        bio = str(normalized.get("bio", ""))
        normalized["emails"] = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", bio)
        normalized["technologies"] = re.findall(r"\b(?:python|go|rust|javascript|typescript|java|kotlin|swift|php|ruby)\b", bio, re.I)
        normalized["intelligence_surface"] = ["commits", "emails", "organizations", "repositories", "forks", "timestamps"]
        return normalized

    async def extract_metadata(self, html: str) -> dict[str, object]:
        soup = tolerant_soup(html)
        bio = soup.find("div", class_="p-note user-profile-bio")
        company = soup.find("li", class_="vcard-detail")
        avatar = soup.find("img", class_="avatar-user")
        metas = meta_map(html)
        metadata = {
            "bio": bio.text.strip() if bio else metas.get("og:description", ""),
            "company": company.text.strip() if company else "",
            "avatar_url": avatar.get("src", "") if avatar else metas.get("og:image", ""),
            "full_name": metas.get("profile:username", "") or metas.get("og:title", "").split("(")[0].strip(),
        }
        metadata["lang_bio"] = detect_lang(str(metadata["bio"]))
        return metadata

    def fingerprint(self, response, text: str) -> bool:
        if response.status != 200:
            return False
        soup = BeautifulSoup(text, "lxml")
        return bool(soup.find("meta", {"property": "og:title"}) or soup.find(attrs={"itemprop": "additionalName"}))

    def confidence(self, metadata: dict[str, object]) -> int:
        if metadata.get("confidence_score"):
            return int(metadata["confidence_score"])
        detection = metadata.get("_detection") if isinstance(metadata.get("_detection"), dict) else {}
        score = int(detection.get("confidence") or 70)
        if metadata.get("bio"):
            score += 10
        if metadata.get("company"):
            score += 10
        return min(99, score)
