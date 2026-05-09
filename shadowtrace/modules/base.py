from __future__ import annotations

from abc import ABC, abstractmethod
from types import SimpleNamespace
from typing import Any

import aiohttp

from shadowtrace.core.models import (
    IntelligenceArtifact,
    ModuleCapability,
    ModuleKind,
    ModulePriority,
    ModuleResult,
    ScanTarget,
    TargetType,
)
from shadowtrace.utils.parser import detect_challenge


class BaseExtractor(ABC):
    """Standard contract for ShadowTrace intelligence modules.

    The legacy username lookup extractors are intentionally promoted to full
    modules.  New modules can override only the stages they need while the
    engine keeps calling the stable ``run -> validate -> collect -> parse ->
    normalize -> enrich -> correlate`` pipeline.
    """

    name: str = ""
    description: str = "Generic ShadowTrace module"
    site_name: str = ""
    url_patterns: tuple[str, ...] = ()
    target_types: tuple[TargetType, ...] = (TargetType.USERNAME,)
    capabilities: tuple[ModuleCapability, ...] = (ModuleCapability.USERNAME_LOOKUP,)
    kind: ModuleKind = ModuleKind.PASSIVE
    priority: ModulePriority = ModulePriority.NORMAL
    rate_limit_key: str | None = None
    url_template: str | None = None
    supports_cache: bool = True

    @property
    def module_name(self) -> str:
        return self.name or self.site_name or self.__class__.__name__

    @classmethod
    def is_url_match(cls, url: str) -> bool:
        return any(pattern in url for pattern in cls.url_patterns)

    async def validate(self, target: ScanTarget) -> bool:
        return target.target_type in self.target_types and bool(str(target.value).strip())

    async def collect(self, target: ScanTarget, context: Any | None = None) -> dict[str, Any]:
        """Collect raw data for the target.

        Platform modules may implement API calls, HTML scraping, JSON parsing,
        dorks, archive lookups, metadata extraction or indirect discovery here.
        The default implementation is deliberately empty so lightweight modules
        can still participate in the pipeline.
        """

        engine = context.get("engine") if isinstance(context, dict) else None
        if engine is None or self.url_template is None:
            return {}
        from shadowtrace.core.session import random_stealth_headers

        session = await engine.http.get()
        url = self.url_template.format(target.value)
        async with session.get(url, headers=random_stealth_headers(engine.config), allow_redirects=True) as response:
            body = await response.content.read(engine.config.max_response_bytes)
            html = body.decode(response.charset or "utf-8", errors="ignore")
            return {"url": url, "status": response.status, "charset": response.charset, "html": html}

    async def parse(self, raw: dict[str, Any], context: Any | None = None) -> dict[str, Any]:
        html = raw.get("html")
        if not html:
            return raw
        response = SimpleNamespace(status=raw.get("status", 0), charset=raw.get("charset"))
        if not self.fingerprint(response, str(html)):
            return {}
        metadata = await self.extract_metadata(str(html))
        metadata["url"] = raw.get("url", "")
        return metadata

    async def normalize(self, parsed: dict[str, Any], context: Any | None = None) -> dict[str, Any]:
        return parsed

    async def enrich(
        self,
        normalized: dict[str, Any],
        shared_results: list[dict[str, Any]] | None = None,
        context: Any | None = None,
    ) -> dict[str, Any]:
        return normalized

    async def correlate(
        self,
        normalized: dict[str, Any],
        shared_results: list[dict[str, Any]] | None = None,
        context: Any | None = None,
    ) -> list[dict[str, Any]]:
        return []

    async def run(
        self,
        target: ScanTarget,
        shared_results: list[dict[str, Any]] | None = None,
        context: Any | None = None,
    ) -> ModuleResult:
        if not await self.validate(target):
            return ModuleResult(module=self.module_name, target=target, status="SKIPPED")
        try:
            raw = await self.collect(target, context=context)
            parsed = await self.parse(raw, context=context)
            normalized = await self.normalize(parsed, context=context)
            enriched = await self.enrich(normalized, shared_results=shared_results, context=context)
            correlations = await self.correlate(enriched, shared_results=shared_results, context=context)
            artifacts = self.to_artifacts(enriched)
            confidence = self.confidence(enriched)
            return ModuleResult(
                module=self.module_name,
                target=target,
                status="FOUND" if artifacts or enriched else "NOT_FOUND",
                artifacts=artifacts,
                normalized=enriched,
                correlations=correlations,
                confidence=confidence,
                risk_score=self.risk_score(enriched, correlations),
            )
        except Exception as exc:
            return ModuleResult(module=self.module_name, target=target, status="ERROR", error=str(exc))

    def to_artifacts(self, normalized: dict[str, Any]) -> list[IntelligenceArtifact]:
        artifacts: list[IntelligenceArtifact] = []
        for key, value in normalized.items():
            if value not in (None, "", [], {}):
                artifacts.append(
                    IntelligenceArtifact(
                        kind=key,
                        value=value,
                        source=self.module_name,
                        confidence=self.confidence(normalized),
                    )
                )
        return artifacts

    def platform_profile(self) -> dict[str, Any]:
        return {
            "name": self.module_name,
            "description": self.description,
            "target_types": [target_type.value for target_type in self.target_types],
            "capabilities": [capability.value for capability in self.capabilities],
            "kind": self.kind.value,
            "priority": int(self.priority),
        }

    @abstractmethod
    async def extract_metadata(self, html: str) -> dict[str, Any]:
        raise NotImplementedError

    def confidence(self, metadata: dict[str, Any]) -> int:
        return 80

    def risk_score(self, metadata: dict[str, Any], correlations: list[dict[str, Any]] | None = None) -> int:
        score = min(100, self.confidence(metadata) // 2)
        if metadata.get("email") or metadata.get("emails"):
            score += 15
        if metadata.get("external_links"):
            score += 5
        if correlations:
            score += min(20, len(correlations) * 5)
        return min(100, score)

    def fingerprint(self, response: aiohttp.ClientResponse, text: str) -> bool:
        return response.status == 200 and len(text) > 100 and not detect_challenge(text)
