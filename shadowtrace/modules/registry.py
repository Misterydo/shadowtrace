from __future__ import annotations

from shadowtrace.modules.base import BaseExtractor
from shadowtrace.modules.github import GitHubExtractor
from shadowtrace.modules.instagram import InstagramExtractor
from shadowtrace.modules.reddit import RedditExtractor
from shadowtrace.modules.twitter import TwitterExtractor

SITES: dict[str, str] = {
    "GitHub": "https://github.com/{}",
    "Instagram": "https://www.instagram.com/{}/",
    "Twitter": "https://twitter.com/{}",
    "Reddit": "https://www.reddit.com/user/{}",
}

EXTRACTORS: dict[str, BaseExtractor] = {
    "GitHub": GitHubExtractor(),
    "Instagram": InstagramExtractor(),
    "Twitter": TwitterExtractor(),
    "Reddit": RedditExtractor(),
}


def find_extractor_for_url(url: str) -> BaseExtractor | None:
    for extractor in EXTRACTORS.values():
        if extractor.is_url_match(url):
            return extractor
    return None


def register_extractor(name: str, url_template: str, extractor: BaseExtractor) -> None:
    SITES[name] = url_template
    EXTRACTORS[name] = extractor
