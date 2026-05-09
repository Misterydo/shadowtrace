from __future__ import annotations

import re

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


def parse_meta_content(html: str, *, property_name: str | None = None, name: str | None = None) -> str:
    soup = BeautifulSoup(html, "lxml")
    attrs: dict[str, str] = {}
    if property_name:
        attrs["property"] = property_name
    if name:
        attrs["name"] = name
    tag = soup.find("meta", attrs=attrs)
    return tag.get("content", "") if tag else ""


def visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()
