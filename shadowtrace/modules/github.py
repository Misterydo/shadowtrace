from __future__ import annotations

from bs4 import BeautifulSoup

from shadowtrace.modules.base import BaseExtractor
from shadowtrace.utils.parser import detect_lang


class GitHubExtractor(BaseExtractor):
    site_name = "GitHub"
    url_patterns = ("github.com",)

    async def extract_metadata(self, html: str) -> dict[str, object]:
        soup = BeautifulSoup(html, "lxml")
        bio = soup.find("div", class_="p-note user-profile-bio")
        company = soup.find("li", class_="vcard-detail")
        avatar = soup.find("img", class_="avatar-user")
        metadata = {
            "bio": bio.text.strip() if bio else "",
            "company": company.text.strip() if company else "",
            "avatar_url": avatar.get("src", "") if avatar else "",
        }
        metadata["lang_bio"] = detect_lang(str(metadata["bio"]))
        return metadata

    def fingerprint(self, response, text: str) -> bool:
        if response.status != 200:
            return False
        soup = BeautifulSoup(text, "lxml")
        return bool(soup.find("meta", {"property": "og:title"}) or soup.find(attrs={"itemprop": "additionalName"}))

    def confidence(self, metadata: dict[str, object]) -> int:
        score = 70
        if metadata.get("bio"):
            score += 10
        if metadata.get("company"):
            score += 10
        return score
