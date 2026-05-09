from __future__ import annotations

import asyncio
from typing import Any

from rapidfuzz import fuzz
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn

from shadowtrace.core.async_manager import async_manager
from shadowtrace.core.cache import cache
from shadowtrace.core.config import CONFIG, ShadowTraceConfig
from shadowtrace.core.logger import console, logger
from shadowtrace.core.models import ProfileResult
from shadowtrace.core.session import HTTPSessionManager, random_stealth_headers, session_manager
from shadowtrace.modules.passive import PassiveIntelEngine
from shadowtrace.core.plugins import discover_plugins
from shadowtrace.modules.registry import EXTRACTORS, SITES
from shadowtrace.utils.fingerprint import extract_avatar_url, hash_avatar
from shadowtrace.utils.retry import backoff_delay
from shadowtrace.utils.validators import validate_username


def smart_username_variants(username: str) -> list[str]:
    variants = {
        username,
        f"{username}123",
        f"{username}_",
        f"_{username}",
        username.replace("a", "4").replace("o", "0"),
        f"{username}.dev",
        f"{username}1",
        username.lower(),
        username.upper(),
        f"real{username}",
        f"the{username}",
        username[::-1],
        f"{username}98",
        f"{username}99",
        f"{username}2000",
        f"{username}2020",
    }
    import re
    variants.add(re.sub(r"[aeio]", "x", username))
    variants.add(username.replace("e", "3"))
    return list(variants)[:12]


def correlation_score(profile_list: list[dict[str, Any]]) -> int:
    if len(profile_list) < 2:
        return 0
    hashes: dict[str, int] = {}
    score = 0
    names: set[str] = set()
    bios: list[str] = []
    for profile in profile_list:
        avatar_hash = profile.get("avatar_hash")
        if avatar_hash:
            if avatar_hash in hashes:
                score += 45
            hashes[str(avatar_hash)] = 1
        metadata = profile.get("metadata", {})
        if metadata.get("bio"):
            bios.append(metadata["bio"])
        name = metadata.get("full_name") or metadata.get("name")
        if name:
            names.add(str(name).lower())
        if metadata.get("passive_score"):
            score += int(metadata["passive_score"]) // 10
    if len(set(bios)) == 1 and bios:
        score += 25
    elif len(bios) > 1:
        fuzzy_scores = [fuzz.ratio(a.lower(), b.lower()) for idx, a in enumerate(bios) for b in bios[idx + 1:]]
        if fuzzy_scores and max(fuzzy_scores) > 60:
            score += 15
    if len(names) == 1 and names:
        score += 20
    return min(99, score)


class ShadowTraceEngine:
    def __init__(self, config: ShadowTraceConfig = CONFIG, http: HTTPSessionManager = session_manager) -> None:
        self.config = config
        self.http = http

    async def initialize(self) -> None:
        discover_plugins()
        await cache.init()

    async def close(self) -> None:
        await self.http.close()
        await cache.close()

    async def try_avatar_hash(self, url: str) -> str | None:
        try:
            session = await self.http.get()
            async with session.get(url, headers=random_stealth_headers(self.config), allow_redirects=True) as response:
                if response.status != 200:
                    return None
                image_bytes = await response.content.read(self.config.max_response_bytes)
                perceptual_hash, md5_hash = hash_avatar(image_bytes)
                return perceptual_hash or md5_hash
        except Exception as exc:
            logger.debug("avatar hash failed for %s: %s", url, exc)
            return None

    async def scan_single(self, username: str, site: str, url_template: str) -> dict[str, Any]:
        cached = await cache.get_profile(username, site)
        if cached and cached.get("status") == "FOUND" and cached.get("last_check"):
            return cached
        session = await self.http.get()
        extractor = EXTRACTORS[site]
        target_url = url_template.format(username)
        last_error: str | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                async with session.get(target_url, headers=random_stealth_headers(self.config), allow_redirects=True) as response:
                    text = await response.content.read(self.config.max_response_bytes)
                    html = text.decode(response.charset or "utf-8", errors="ignore")
                    found = extractor.fingerprint(response, html)
                    metadata = await extractor.extract_metadata(html) if found else {}
                    avatar_url = extract_avatar_url(metadata)
                    avatar_hash = await self.try_avatar_hash(avatar_url) if avatar_url else None
                    result = ProfileResult(
                        site=site,
                        username=username,
                        url=target_url,
                        status="FOUND" if found else "NOT FOUND",
                        metadata=metadata,
                        avatar_hash=avatar_hash,
                        confidence=extractor.confidence(metadata),
                    )
                    if found:
                        await cache.set_profile(username, site, target_url, True, result.confidence, avatar_hash, metadata)
                    return result.to_dict()
            except asyncio.TimeoutError:
                last_error = "timeout"
            except Exception as exc:
                last_error = str(exc)
            if attempt < self.config.max_retries:
                await asyncio.sleep(backoff_delay(attempt))
        return ProfileResult(site, username, target_url, "ERROR", error=last_error).to_dict()

    async def scan_username(self, username: str, mode: str = "single", passive: bool = False) -> tuple[list[dict], list[dict]]:
        clean_username = validate_username(username)
        variants = [clean_username] if mode == "single" else smart_username_variants(clean_username)
        coroutines = [self.scan_single(candidate, site, url_template) for candidate in variants for site, url_template in SITES.items()]
        profiles: list[dict] = []
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            transient=True,
        ) as progress:
            task = progress.add_task("[cyan]Scanning...", total=len(coroutines))
            async def tracked(coro):
                result = await coro
                progress.advance(task)
                return result
            profiles = await async_manager.gather_limited([tracked(coro) for coro in coroutines])
        passive_results: list[dict] = []
        if passive:
            passive_engine = PassiveIntelEngine(clean_username, config=self.config, http=self.http)
            passive_results = await passive_engine.run()
            PassiveIntelEngine.rich_show(passive_results)
            for profile in profiles:
                profile["metadata"] = PassiveIntelEngine.enrich_metadata(profile.get("metadata", {}), passive_results)
        return [profile for profile in profiles if profile], passive_results


engine = ShadowTraceEngine()
