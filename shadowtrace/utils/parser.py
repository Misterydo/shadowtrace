from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

import langdetect
from bs4 import BeautifulSoup

CHALLENGE_TRIGGERS = (
    "unusual traffic", "detected unusual traffic", "captcha", "attention required",
    "cloudflare", "access denied", "unusual requests", "to continue, please",
    "please verify you are a human", "rate limit exceeded",
)


def detect_challenge(text: str) -> bool:
    lowered = text.lower()
    return any(trigger in lowered for trigger in CHALLENGE_TRIGGERS)


def detect_lang(text: str) -> str:
    if not text.strip():
        return "unknown"
    try:
        return langdetect.detect(text)
    except Exception:
        return "unknown"


def tolerant_soup(html: str) -> BeautifulSoup:
    """Parse complete, partial or malformed HTML without raising to callers."""

    try:
        return BeautifulSoup(html or "", "lxml")
    except Exception:
        return BeautifulSoup(html or "", "html.parser")


def parse_meta_content(html: str, *, property_name: str | None = None, name: str | None = None) -> str:
    soup = tolerant_soup(html)
    attrs: dict[str, str] = {}
    if property_name:
        attrs["property"] = property_name
    if name:
        attrs["name"] = name
    tag = soup.find("meta", attrs=attrs)
    return tag.get("content", "") if tag else ""


def meta_map(html: str) -> dict[str, str]:
    soup = tolerant_soup(html)
    metadata: dict[str, str] = {}
    for tag in soup.find_all("meta"):
        key = tag.get("property") or tag.get("name") or tag.get("itemprop")
        value = tag.get("content")
        if key and value:
            metadata[str(key).lower()] = str(value).strip()
    return metadata


def title_text(html: str) -> str:
    soup = tolerant_soup(html)
    title = soup.find("title")
    return title.get_text(" ", strip=True) if title else ""


def canonical_url(html: str) -> str:
    soup = tolerant_soup(html)
    link = soup.find("link", rel=lambda value: value and "canonical" in value)
    return link.get("href", "") if link else ""


def visible_text(html: str) -> str:
    soup = tolerant_soup(html)
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


def iter_json_blobs(html: str) -> Iterator[Any]:
    """Yield JSON objects from ld+json, Next/data and common hydration snippets."""

    soup = tolerant_soup(html)
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        if not text.strip():
            continue
        script_type = str(script.get("type", "")).lower()
        if "json" in script_type:
            try:
                yield json.loads(text.strip())
            except json.JSONDecodeError:
                continue
        for pattern in (
            r"window\._sharedData\s*=\s*({.*?})\s*;\s*</script>",
            r"window\.__INITIAL_STATE__\s*=\s*({.*?})\s*;",
            r"__NEXT_DATA__[^>]*>\s*({.*?})\s*</script>",
        ):
            for match in re.finditer(pattern, str(script), re.S):
                try:
                    yield json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue
