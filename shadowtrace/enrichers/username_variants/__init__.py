from __future__ import annotations

import re
from collections.abc import Iterable

_YEAR_RE = re.compile(r"^(?P<name>[A-Za-z][A-Za-z._-]*?)(?P<year>(?:19|20)\d{2}|\d{2})$")
_SEPARATORS = ("_", ".", "-")
_PREFIXES = ("real", "its", "the")
_SUFFIXES = ("dev", "x", "exe", "official")


def _dedupe(values: Iterable[str], limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip().lstrip("@").lower()
        if not cleaned or cleaned in seen or len(cleaned) > 64:
            continue
        seen.add(cleaned)
        result.append(cleaned)
        if len(result) >= limit:
            break
    return result


def generate_username_variants(username: str, *, limit: int = 32) -> list[str]:
    """Generate conservative, contextual username mutations.

    This is deliberately deterministic and small; ShadowTrace should avoid noisy
    botnet-style probing while still checking common reused identity patterns.
    """

    base = username.strip().lstrip("@").lower()
    compact = re.sub(r"[._-]+", "", base)
    candidates: list[str] = [base]
    if compact != base:
        candidates.append(compact)

    match = _YEAR_RE.match(compact)
    if match:
        name = match.group("name")
        year = match.group("year")
        short_year = year[-2:]
        for sep in _SEPARATORS:
            candidates.append(f"{name}{sep}{year}")
            candidates.append(f"{name}{sep}{short_year}")
        candidates.extend((f"real{name}{year}", f"its{name}{year}", f"{name}{short_year}"))
    else:
        for prefix in _PREFIXES:
            candidates.append(f"{prefix}{compact}")
        for suffix in _SUFFIXES:
            candidates.append(f"{compact}{suffix}")
            candidates.append(f"{compact}_{suffix}")
        candidates.append(f"{compact}123")

    return _dedupe(candidates, limit)
