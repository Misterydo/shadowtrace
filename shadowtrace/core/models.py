from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ProfileStatus = Literal["FOUND", "NOT FOUND", "ERROR"]


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
