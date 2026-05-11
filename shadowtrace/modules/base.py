from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import aiohttp
from rapidfuzz import fuzz

from shadowtrace.core.models import (
    IntelligenceArtifact,
    ModuleCapability,
    ModuleKind,
    ModulePriority,
    ModuleResult,
    ScanTarget,
    TargetType,
    UniversalProfile,
)
from shadowtrace.utils.parser import canonical_url, detect_challenge, meta_map, title_text


class BaseExtractor(ABC):
    """Standard contract for resilient, layered ShadowTrace modules.

    Username/profile modules are intentionally split into three independent
    layers: heuristic existence detection, best-effort metadata extraction and
    lightweight enrichment/correlation.  Extraction failures never invalidate
    Layer 1 existence decisions.
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
    positive_patterns: tuple[str, ...] = ()
    negative_patterns: tuple[str, ...] = (
        "not found", "page not found", "profile not found", "user not found",
        "user does not exist", "account doesn't exist", "this account doesn't exist",
        "sorry, nobody on reddit goes by that name", "couldn't find this account",
    )

    @property
    def module_name(self) -> str:
        return self.name or self.site_name or self.__class__.__name__

    @classmethod
    def is_url_match(cls, url: str) -> bool:
        return any(pattern in url for pattern in cls.url_patterns)

    async def validate(self, target: ScanTarget) -> bool:
        return target.target_type in self.target_types and bool(str(target.value).strip())

    def profile_url(self, username: str) -> str:
        if not self.url_template:
            return username
        return self.url_template.format(username)

    async def collect(self, target: ScanTarget, context: Any | None = None) -> dict[str, Any]:
        """Collect raw HTML without doing existence or extraction decisions."""

        engine = context.get("engine") if isinstance(context, dict) else None
        if engine is None or self.url_template is None:
            return {}
        from shadowtrace.core.session import fetch_text

        session = await engine.http.get()
        return await fetch_text(session, self.profile_url(str(target.value)), engine.config)

    async def check_exists(self, username: str, raw: dict[str, Any] | None = None, context: Any | None = None) -> dict[str, Any]:
        """Phase 1: fast existence check based on status, redirects and page fingerprints."""

        if raw is None:
            engine = context.get("engine") if isinstance(context, dict) else None
            if engine is None:
                raw = {}
            else:
                from shadowtrace.core.session import fetch_text

                session = await engine.http.get()
                raw = await fetch_text(session, self.profile_url(username), engine.config)
        return self.heuristic_detect(raw or {}, username)

    async def detect(self, username: str, raw: dict[str, Any] | None = None, context: Any | None = None) -> dict[str, Any]:
        """Backward-compatible alias for Phase 1 existence detection."""

        return await self.check_exists(username, raw=raw, context=context)

    async def extract_basic(
        self,
        username: str,
        html: str | None = None,
        raw: dict[str, Any] | None = None,
        context: Any | None = None,
    ) -> dict[str, Any]:
        """Phase 2: basic HTML/embedded-JSON extraction without browser automation."""

        if html is None:
            if raw is None:
                engine = context.get("engine") if isinstance(context, dict) else None
                if engine is None:
                    html = ""
                else:
                    from shadowtrace.core.session import fetch_text

                    session = await engine.http.get()
                    raw = await fetch_text(session, self.profile_url(username), engine.config)
            html = str((raw or {}).get("html", ""))
        return await self.extract_metadata(html or "")

    async def extract_advanced(
        self,
        username: str,
        raw: dict[str, Any] | None = None,
        context: Any | None = None,
    ) -> dict[str, Any]:
        """Phase 3: optional dynamic/API/browser enrichment hook. Disabled by default."""

        return {}

    async def extract(
        self,
        username: str,
        html: str | None = None,
        raw: dict[str, Any] | None = None,
        context: Any | None = None,
    ) -> dict[str, Any]:
        """Layer 2: best-effort metadata extraction, isolated from detection."""

        basic = await self.extract_basic(username, html=html, raw=raw, context=context)
        advanced = await self.extract_advanced(username, raw=raw, context=context)
        merged = dict(basic or {})
        merged.update({key: value for key, value in (advanced or {}).items() if value not in (None, "", [], {})})
        return merged

    def heuristic_detect(self, raw: dict[str, Any], username: str = "") -> dict[str, Any]:
        html = str(raw.get("html") or "")
        lowered = html.lower()
        status = int(raw.get("status") or 0)
        headers = raw.get("headers") or {}
        content_length = int(raw.get("content_length") or len(html.encode("utf-8", errors="ignore")))
        title = title_text(html)
        metadata = meta_map(html)
        canonical = canonical_url(html)
        final_url = str(raw.get("final_url") or raw.get("url") or "")
        score = 0
        signals: dict[str, Any] = {
            "status": status,
            "status_200": status == 200,
            "status_2xx": 200 <= status < 300,
            "redirects": bool(raw.get("history")),
            "content_length": content_length,
            "html_title": bool(title),
            "title": title[:160],
            "canonical_url": canonical,
            "final_url": final_url,
            "og_title": bool(metadata.get("og:title")),
            "og_description": bool(metadata.get("og:description")),
            "og_url": metadata.get("og:url", ""),
            "generic_html": "<html" in lowered or "<body" in lowered or content_length > 300,
            "challenge_detected": detect_challenge(html),
        }
        if status == 200:
            score += 30
        elif status in (301, 302, 303, 307, 308):
            score += 16
        elif status in (401, 403, 429):
            score += 12
        elif status == 404:
            score -= 45
        elif status >= 500:
            score -= 10
        if signals["generic_html"]:
            score += 12
        if content_length > 1000:
            score += 12
        elif content_length > 150:
            score += 5
        if title:
            score += 8
        if metadata.get("og:title"):
            score += 14
        if metadata.get("og:description"):
            score += 8
        if canonical:
            score += 8
        if username:
            uname = username.lower().strip("/@")
            urlish = " ".join([canonical, final_url, metadata.get("og:url", "")]).lower()
            titleish = " ".join([title, metadata.get("og:title", ""), metadata.get("og:description", "")]).lower()
            if uname and uname in urlish:
                signals["username_in_url"] = True
                score += 15
            if uname and uname in titleish:
                signals["username_in_metadata"] = True
                score += 12
        positives = [pattern for pattern in self.positive_patterns if pattern.lower() in lowered]
        negatives = [pattern for pattern in self.negative_patterns if pattern.lower() in lowered]
        signals["positive_patterns"] = positives[:10]
        signals["negative_patterns"] = negatives[:10]
        if positives:
            score += min(24, len(positives) * 8)
        if negatives:
            score -= min(50, len(negatives) * 18)
        if signals["challenge_detected"] and status != 404:
            signals["blocked_or_challenged_but_maybe_exists"] = True
            score = max(score, 35)
        if headers.get("location") and username.lower() in str(headers.get("location", "")).lower():
            score += 8
        confidence = max(0, min(99, score))
        exists = confidence >= 45 or (status in (401, 403, 429) and content_length > 0 and not negatives)
        return {"exists": bool(exists), "confidence": confidence, "signals": signals}

    async def parse(self, raw: dict[str, Any], context: Any | None = None) -> dict[str, Any]:
        username = ""
        if isinstance(context, dict):
            username = str(context.get("username") or "")
        detection = await self.detect(username, raw=raw, context=context)
        parsed: dict[str, Any] = {"_detection": detection, "url": raw.get("url", ""), "final_url": raw.get("final_url", raw.get("url", ""))}
        if not detection.get("exists"):
            return parsed
        try:
            metadata = await self.extract(username, html=str(raw.get("html", "")), raw=raw, context=context)
            parsed.update(metadata or {})
        except Exception as exc:
            parsed["_extraction_error"] = str(exc)
        return parsed

    async def normalize(self, parsed: dict[str, Any], context: Any | None = None) -> dict[str, Any]:
        return parsed

    def normalize_profile(self, normalized: dict[str, Any], username: str = "") -> UniversalProfile:
        detection = normalized.get("_detection") if isinstance(normalized.get("_detection"), dict) else {}
        exists = bool(detection.get("exists"))
        confidence = int(normalized.get("confidence_score") or detection.get("confidence") or self.confidence(normalized))
        return UniversalProfile.from_metadata(
            platform=self.module_name.lower(),
            username=username,
            exists=exists,
            metadata=normalized,
            confidence=confidence,
        )

    async def enrich(
        self,
        normalized: dict[str, Any],
        shared_results: list[dict[str, Any]] | None = None,
        context: Any | None = None,
    ) -> dict[str, Any]:
        """Layer 3: add practical confidence/correlation hints without scraping assumptions."""

        enriched = dict(normalized)
        detection = enriched.get("_detection", {}) if isinstance(enriched.get("_detection"), dict) else {}
        score = int(detection.get("confidence") or self.confidence(enriched))
        username = str(context.get("username") or "") if isinstance(context, dict) else ""
        text_bits = " ".join(str(enriched.get(key, "")) for key in ("bio", "description", "full_name", "title", "name"))
        if username and text_bits.strip():
            enriched["username_similarity"] = fuzz.partial_ratio(username.lower(), text_bits.lower())
            if enriched["username_similarity"] > 70:
                score += 5
        if enriched.get("avatar_url"):
            enriched["avatar_present"] = True
            score += 5
        if enriched.get("bio") or enriched.get("description"):
            score += 5
        enriched["confidence_score"] = max(0, min(99, score))
        return enriched

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
        context_data = dict(context or {}) if isinstance(context, dict) else {}
        context_data.setdefault("username", str(target.value))
        try:
            raw = await self.collect(target, context=context_data)
            parsed = await self.parse(raw, context=context_data)
            normalized = await self.normalize(parsed, context=context_data)
            enriched = await self.enrich(normalized, shared_results=shared_results, context=context_data)
            correlations = await self.correlate(enriched, shared_results=shared_results, context=context_data)
            universal_profile = self.normalize_profile(enriched, str(target.value))
            enriched["universal_profile"] = universal_profile.to_dict()
            artifacts = self.to_artifacts(enriched)
            confidence = self.confidence(enriched)
            exists = bool(enriched.get("_detection", {}).get("exists")) if isinstance(enriched.get("_detection"), dict) else bool(enriched)
            return ModuleResult(
                module=self.module_name,
                target=target,
                status="FOUND" if exists else "NOT_FOUND",
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
            if key.startswith("_"):
                continue
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
            "pipeline": ["check_exists", "extract_basic", "extract_advanced", "normalize", "enrich"],
        }

    @abstractmethod
    async def extract_metadata(self, html: str) -> dict[str, Any]:
        raise NotImplementedError

    def confidence(self, metadata: dict[str, Any]) -> int:
        if metadata.get("confidence_score"):
            return int(metadata["confidence_score"])
        detection = metadata.get("_detection") if isinstance(metadata.get("_detection"), dict) else {}
        return int(detection.get("confidence") or 80)

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
        raw = {"status": response.status, "charset": getattr(response, "charset", None), "html": text, "content_length": len(text)}
        return bool(self.heuristic_detect(raw).get("exists"))


class PlatformModule(BaseExtractor):
    """Semantic base class for universal platform modules.

    New platform integrations should inherit from this name and implement the
    four-phase contract: check_exists(), extract_basic(), extract_advanced(),
    and normalize(). Existing extractors keep working through BaseExtractor.
    """

    pass
