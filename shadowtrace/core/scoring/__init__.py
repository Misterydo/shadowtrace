from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ConfidenceBand(StrEnum):
    WEAK = "weak"
    POSSIBLE = "possible"
    STRONG = "strong"
    NEAR_CERTAIN = "near_certain"


@dataclass(frozen=True, slots=True)
class EvidenceWeights:
    """Default points for identity-correlation evidence.

    The values intentionally match ShadowTrace's public architecture notes so
    platform modules and future enrichers can share one scoring vocabulary.
    """

    same_username: int = 40
    same_avatar: int = 80
    same_external_link: int = 90
    similar_bio: int = 30
    same_display_name: int = 20
    same_domain: int = 50


@dataclass(slots=True)
class ScoreEvidence:
    kind: str
    points: int
    description: str
    source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "kind": self.kind,
            "points": self.points,
            "description": self.description,
            "metadata": self.metadata,
        }
        if self.source:
            data["source"] = self.source
        return data


@dataclass(slots=True)
class CorrelationScore:
    score: int
    band: ConfidenceBand
    evidence: list[ScoreEvidence] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "band": self.band.value,
            "evidence": [item.to_dict() for item in self.evidence],
        }


def confidence_band(score: int) -> ConfidenceBand:
    if score <= 30:
        return ConfidenceBand.WEAK
    if score <= 60:
        return ConfidenceBand.POSSIBLE
    if score <= 85:
        return ConfidenceBand.STRONG
    return ConfidenceBand.NEAR_CERTAIN


def score_from_evidence(evidence: list[ScoreEvidence]) -> CorrelationScore:
    score = max(0, min(100, sum(item.points for item in evidence)))
    return CorrelationScore(score=score, band=confidence_band(score), evidence=evidence)
