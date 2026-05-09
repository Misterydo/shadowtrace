from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import IntEnum, StrEnum
from typing import Any, Literal

ProfileStatus = Literal["FOUND", "NOT FOUND", "ERROR"]
ModuleRunStatus = Literal["FOUND", "NOT_FOUND", "SKIPPED", "ERROR"]


class TargetType(StrEnum):
    USERNAME = "username"
    EMAIL = "email"
    PHONE = "phone"
    DOMAIN = "domain"
    URL = "url"
    IP_ADDRESS = "ip_address"
    CRYPTO_WALLET = "crypto_wallet"
    DOCUMENT = "document"
    IMAGE = "image"
    SOCIAL_PROFILE = "social_profile"
    IOC = "ioc"


class ModuleKind(StrEnum):
    PASSIVE = "passive"
    ACTIVE = "active"
    HYBRID = "hybrid"


class ModuleCapability(StrEnum):
    USERNAME_LOOKUP = "username_lookup"
    EMAIL_INTELLIGENCE = "email_intelligence"
    PHONE_INTELLIGENCE = "phone_intelligence"
    DOMAIN_INTELLIGENCE = "domain_intelligence"
    DNS_ENUMERATION = "dns_enumeration"
    WHOIS_LOOKUP = "whois_lookup"
    SUBDOMAIN_ENUMERATION = "subdomain_enumeration"
    SOCIAL_SCRAPING = "social_scraping"
    PUBLIC_BREACH_ANALYSIS = "public_breach_analysis"
    METADATA_EXTRACTION = "metadata_extraction"
    GEOLOCATION_CORRELATION = "geolocation_correlation"
    PASTE_LEAK_INDEXING = "paste_leak_indexing"
    GITHUB_INTELLIGENCE = "github_intelligence"
    DARK_WEB_INDEXING = "dark_web_indexing"
    ARCHIVE_ANALYSIS = "archive_analysis"
    REVERSE_SEARCH = "reverse_search"
    PROFILE_CORRELATION = "profile_correlation"
    AI_ASSISTED_ANALYSIS = "ai_assisted_analysis"
    THREAT_INTELLIGENCE = "threat_intelligence"
    IOC_ANALYSIS = "ioc_analysis"
    URL_INTELLIGENCE = "url_intelligence"
    CRYPTO_WALLET_TRACKING = "crypto_wallet_tracking"
    PLATFORM_ENUMERATION = "platform_enumeration"
    REPUTATION_ANALYSIS = "reputation_analysis"
    RISK_SCORING = "risk_scoring"
    TIMELINE_GENERATION = "timeline_generation"


class ModulePriority(IntEnum):
    LOW = 25
    NORMAL = 50
    HIGH = 75
    CRITICAL = 100


@dataclass(slots=True)
class ScanTarget:
    value: str
    target_type: TargetType = TargetType.USERNAME
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["target_type"] = self.target_type.value
        return data


@dataclass(slots=True)
class IntelligenceArtifact:
    kind: str
    value: Any
    source: str
    confidence: int = 0
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ModuleResult:
    module: str
    target: ScanTarget
    status: ModuleRunStatus
    artifacts: list[IntelligenceArtifact] = field(default_factory=list)
    normalized: dict[str, Any] = field(default_factory=dict)
    correlations: list[dict[str, Any]] = field(default_factory=list)
    confidence: int = 0
    risk_score: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["target"] = self.target.to_dict()
        data["artifacts"] = [artifact.to_dict() for artifact in self.artifacts]
        return {k: v for k, v in data.items() if v is not None}


@dataclass(slots=True)
class ProfileResult:
    site: str
    username: str
    url: str
    status: ProfileStatus
    confidence: int = 0
    avatar_hash: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    cached: bool = False
    last_check: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(slots=True)
class PassiveResult:
    engine: str
    dork: str
    snippets: list[dict[str, str]]
    score: int
    cache: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}
