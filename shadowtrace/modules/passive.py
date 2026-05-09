from __future__ import annotations

import asyncio
import random
import time
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from rich import box
from rich.table import Table

from shadowtrace.core.cache import cache
from shadowtrace.core.config import CONFIG, ShadowTraceConfig
from shadowtrace.core.logger import console, logger
from shadowtrace.core.models import PassiveResult
from shadowtrace.core.session import HTTPSessionManager, random_stealth_headers, session_manager
from shadowtrace.utils.parser import detect_challenge
from shadowtrace.utils.retry import backoff_delay


class PassiveIntelEngine:
    def __init__(
        self,
        username: str,
        engines: tuple[str, ...] = ("bing",),
        config: ShadowTraceConfig = CONFIG,
        http: HTTPSessionManager = session_manager,
    ) -> None:
        self.username = username
        self.engines = engines
        self.config = config
        self.http = http

    def build_bing_dorks(self) -> list[str]:
        user = self.username
        return [
            f'site:instagram.com "{user}"',
            f'site:github.com "{user}"',
            f'site:twitter.com "{user}"',
            f'site:reddit.com "{user}"',
            f'site:instagram.com "{user}" "@"',
            f'site:instagram.com "{user}" "/p/"',
            f'site:instagram.com "{user}" "comentou"',
            f'site:instagram.com "{user}" "bio"',
        ]

    async def run(self) -> list[dict]:
        results: list[dict] = []
        last_request = 0.0
        for engine in self.engines:
            if engine != "bing":
                continue
            for query in self.build_bing_dorks():
                wait_for = self.config.passive_rate_limit_sec + random.uniform(0.3, 0.9) - (time.time() - last_request)
                if wait_for > 0:
                    await asyncio.sleep(wait_for)
                last_request = time.time()
                cached = await cache.get_passive(engine, query, self.username)
                if cached:
                    results.append(PassiveResult(engine, query, cached["snippets"], cached["score"], cache=True).to_dict())
                    continue
                results.append((await self._query_bing(query)).to_dict())
        return results

    async def _query_bing(self, query: str) -> PassiveResult:
        session = await self.http.get()
        url = f"https://www.bing.com/search?q={quote_plus(query)}&count=7"
        for attempt in range(self.config.max_retries + 1):
            try:
                async with session.get(url, headers=random_stealth_headers(self.config), allow_redirects=True) as response:
                    html = await response.text(errors="ignore")
                    if detect_challenge(html):
                        logger.warning("[PASSIVE] Bing challenge detected; applying cooldown")
                        await asyncio.sleep(30 + random.randint(5, 25))
                        continue
                    snippets = self.parse_bing_results(html)
                    score = self.passive_score(snippets)
                    await cache.set_passive("bing", query, self.username, snippets, score)
                    return PassiveResult("bing", query, snippets, score)
            except asyncio.TimeoutError:
                if attempt >= self.config.max_retries:
                    return PassiveResult("bing", query, [], 0, error="timeout")
            except Exception as exc:
                if attempt >= self.config.max_retries:
                    return PassiveResult("bing", query, [], 0, error=str(exc))
            await asyncio.sleep(backoff_delay(attempt))
        return PassiveResult("bing", query, [], 0, error="challenge_or_retry_exhausted")

    @staticmethod
    def parse_bing_results(html: str) -> list[dict[str, str]]:
        soup = BeautifulSoup(html, "lxml")
        results: list[dict[str, str]] = []
        for block in soup.find_all("li", {"class": "b_algo"}):
            link = block.find("a")
            paragraph = block.find("p")
            results.append({
                "title": link.text.strip() if link else "",
                "link": link.get("href", "") if link else "",
                "desc": paragraph.text.strip() if paragraph else "",
                "context": block.text.strip(),
            })
        return results

    def passive_score(self, results: list[dict[str, str]]) -> int:
        score = 0
        user = self.username.lower()
        for result in results:
            context = result.get("context", "").lower()
            local_score = 0
            if user in context:
                local_score += 10
            if "instagram.com/p/" in context:
                local_score += 10
            if "bio" in context:
                local_score += 12
            if "comment" in context or "comentou" in context:
                local_score += 10
            if f"@{user}" in context:
                local_score += 8
            if "followers" in context:
                local_score += 4
            if "avatar" in context:
                local_score += 5
            if "twitter.com/" in context or "x.com/" in context:
                local_score += 5
            if local_score == 0 and user in result.get("desc", "").lower():
                local_score = 8
            score += local_score
        return min(100, score)

    @staticmethod
    def rich_show(passive_results: list[dict]) -> None:
        table = Table(title="Passive OSINT (Bing)", box=box.ROUNDED)
        table.add_column("Dork")
        table.add_column("Score", justify="center")
        table.add_column("Top Link / Context")
        for result in passive_results:
            dork = result.get("dork", "")
            snippets = result.get("snippets", [])
            top = snippets[0]["link"] if snippets else "-"
            context = snippets[0]["context"][:70] if snippets else "-"
            table.add_row(dork[:38] + ("..." if len(dork) > 38 else ""), str(result.get("score", 0)), f"{top}\n{context}")
        console.print(table)

    @staticmethod
    def enrich_metadata(metadata: dict, passive_results: list[dict]) -> dict:
        enriched = dict(metadata)
        enriched["passive_score"] = max((item.get("score", 0) for item in passive_results), default=0)
        return enriched
