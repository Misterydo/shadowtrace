from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn

from shadowtrace.core.async_manager import async_manager
from shadowtrace.core.cache import cache
from shadowtrace.core.config import CONFIG, ShadowTraceConfig
from shadowtrace.core.events import event_bus
from shadowtrace.core.logger import console, logger
from shadowtrace.core.models import ProfileResult, ScanTarget, TargetType
from shadowtrace.core.rate_limit import rate_limiter
from shadowtrace.core.session import HTTPSessionManager, fetch_text, random_stealth_headers, session_manager
from shadowtrace.modules.passive import PassiveIntelEngine
from shadowtrace.core.plugins import discover_plugins
from shadowtrace.modules.registry import MODULE_REGISTRY
from shadowtrace.utils.fingerprint import extract_avatar_url, hash_avatar
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
        discover_plugins(self.config.plugin_paths)
        rate_limiter.global_interval = self.config.global_rate_limit_sec
        for key, interval in self.config.module_rate_limits_sec.items():
            rate_limiter.configure(key, interval)
        await cache.init()
        await event_bus.emit("engine.initialized", modules=MODULE_REGISTRY.describe())

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

    async def dump_debug_html(self, site: str, username: str, html: str) -> None:
        if not self.config.debug_html_dump or not html:
            return
        safe_site = re.sub(r"[^A-Za-z0-9_.-]+", "_", site)
        safe_username = re.sub(r"[^A-Za-z0-9_.-]+", "_", username)
        debug_dir = Path(self.config.debug_dir)
        if not debug_dir.is_absolute():
            debug_dir = Path.cwd() / debug_dir
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / f"{safe_site}_{safe_username}.html").write_text(html, encoding="utf-8", errors="ignore")

    async def scan_single(self, username: str, site: str, url_template: str) -> dict[str, Any]:
        cached = await cache.get_profile(username, site)
        if cached and cached.get("status") == "FOUND" and cached.get("last_check"):
            return cached
        session = await self.http.get()
        extractor = MODULE_REGISTRY.module(site)
        target_url = url_template.format(username)
        try:
            await rate_limiter.wait(extractor.rate_limit_key or site)
            await event_bus.emit("module.started", module=site, target=username, url=target_url)
            raw = await fetch_text(session, target_url, self.config)
            html = str(raw.get("html", ""))
            await self.dump_debug_html(site, username, html)
            detection = await extractor.detect(username, raw=raw, context={"engine": self, "url": target_url, "username": username})
            found = bool(detection.get("exists"))
            metadata: dict[str, Any] = {"_detection": detection}
            if found:
                try:
                    extracted = await extractor.extract(username, html=html, raw=raw, context={"engine": self, "url": target_url, "username": username})
                    metadata.update(extracted or {})
                except Exception as exc:
                    metadata["_extraction_error"] = str(exc)
                metadata = await extractor.normalize(metadata, context={"engine": self, "url": target_url, "username": username})
                metadata = await extractor.enrich(metadata, context={"engine": self, "url": target_url, "username": username})
            avatar_url = extract_avatar_url(metadata)
            avatar_hash = await self.try_avatar_hash(avatar_url) if avatar_url else None
            confidence = extractor.confidence(metadata)
            result = ProfileResult(
                site=site,
                username=username,
                url=str(raw.get("final_url") or target_url),
                status="FOUND" if found else "NOT FOUND",
                metadata=metadata,
                avatar_hash=avatar_hash,
                confidence=confidence,
                error=raw.get("error"),
            )
            if found:
                await cache.set_profile(username, site, target_url, True, result.confidence, avatar_hash, metadata)
            payload = result.to_dict()
            await event_bus.emit("module.completed", module=site, target=username, result=payload)
            return payload
        except asyncio.TimeoutError:
            last_error = "timeout"
        except Exception as exc:
            last_error = str(exc)
        result = ProfileResult(site, username, target_url, "ERROR", error=last_error).to_dict()
        await event_bus.emit("module.failed", module=site, target=username, error=last_error)
        return result

    async def scan_username(self, username: str, mode: str = "single", passive: bool = False) -> tuple[list[dict], list[dict]]:
        clean_username = validate_username(username)
        variants = [clean_username] if mode == "single" else smart_username_variants(clean_username)
        coroutines = [self.scan_single(candidate, site, url_template) for candidate in variants for site, url_template, _module in MODULE_REGISTRY.items()]
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
        await event_bus.emit("scan.completed", target=clean_username, profiles=profiles, passive=passive_results)
        return [profile for profile in profiles if profile], passive_results

    async def run_modules_for_target(self, target_value: str, target_type: TargetType = TargetType.USERNAME) -> list[dict[str, Any]]:
        """Run decoupled modules by declared target type for future API/UI workers."""

        target = ScanTarget(target_value, target_type)
        shared_results: list[dict[str, Any]] = []
        for module in MODULE_REGISTRY.modules_for_target(target_type):
            await rate_limiter.wait(module.rate_limit_key or module.module_name)
            await event_bus.emit("module.pipeline.started", module=module.module_name, target=target.to_dict())
            result = await module.run(target, shared_results=shared_results, context={"engine": self})
            payload = result.to_dict()
            shared_results.append(payload)
            await event_bus.emit("module.pipeline.completed", module=module.module_name, result=payload)
        return shared_results


engine = ShadowTraceEngine()
