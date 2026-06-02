"""Pydantic models for LLM structured outputs.

OpusFindings — Stage [3] output schema (top-K full-flatten findings list).
HaikuSummary — Stage [4] per-session compact summary.
ClusterFinding — Stage [5] cross-session cluster output.
Candidate     — merged + normalized representation handed to dedup/redact/emit.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Severity = Literal["low", "medium", "high"]
_INTENT_CATEGORIES = {
    "refactor", "bugfix", "feature", "exploration", "docs", "infra", "other",
}
_TRAJECTORY_QUALITIES = {"smooth", "hesitant", "chaotic", "stuck"}


class Finding(BaseModel):
    pattern_id: str
    title: str
    severity: Severity
    frequency_in_sample: int
    session_examples: list[str] = Field(default_factory=list)
    mast_taxonomy: str = "OTHER"
    symptom: str
    proposed_fix: str
    evidence_quotes: list[str] = Field(default_factory=list)

    @field_validator("session_examples", "evidence_quotes", mode="before")
    @classmethod
    def _truncate_lists(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(x) for x in v[:3] if x is not None]


class OpusFindings(BaseModel):
    findings: list[Finding] = Field(default_factory=list)


class HaikuSummary(BaseModel):
    session_id: str
    summary: str
    user_intent_category: str = "other"
    tools_chained: list[str] = Field(default_factory=list)
    errors_encountered: list[str] = Field(default_factory=list)
    failure_mode_hint: str = "NONE"
    trajectory_quality: str = "smooth"
    actionable_pattern_seed: str | None = None

    @field_validator("user_intent_category", mode="before")
    @classmethod
    def _coerce_intent(cls, v: object) -> str:
        if isinstance(v, str) and v in _INTENT_CATEGORIES:
            return v
        return "other"

    @field_validator("trajectory_quality", mode="before")
    @classmethod
    def _coerce_trajectory(cls, v: object) -> str:
        if isinstance(v, str) and v in _TRAJECTORY_QUALITIES:
            return v
        return "smooth"

    @field_validator("errors_encountered", "tools_chained", mode="before")
    @classmethod
    def _truncate_lists(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        out = [str(x) for x in v[:3] if x is not None]
        return out


class ClusterFinding(BaseModel):
    name: str
    description: str
    frequency: int
    session_ids: list[str] = Field(default_factory=list)


class Candidate(BaseModel):
    source: Literal["opus_top_k", "cluster", "haiku_seed"]
    pattern_id: str
    title: str
    severity: Severity = "medium"
    frequency: int = 1
    examples: list[str] = Field(default_factory=list)
    symptom: str
    proposed_fix: str
    evidence_quotes: list[str] = Field(default_factory=list)
    mast_taxonomy: str | None = None

    @classmethod
    def from_opus(cls, f: Finding) -> "Candidate":
        return cls(
            source="opus_top_k",
            pattern_id=f.pattern_id,
            title=f.title,
            severity=f.severity,
            frequency=f.frequency_in_sample,
            examples=list(f.session_examples),
            symptom=f.symptom,
            proposed_fix=f.proposed_fix,
            evidence_quotes=list(f.evidence_quotes),
            mast_taxonomy=f.mast_taxonomy,
        )

    @classmethod
    def from_cluster(cls, c: ClusterFinding) -> "Candidate":
        slug = (
            c.name.lower()
            .replace(" ", "-")
            .replace("_", "-")
            .replace("/", "-")
        )
        slug = "".join(ch for ch in slug if ch.isalnum() or ch == "-").strip("-") or "cluster"
        return cls(
            source="cluster",
            pattern_id=slug,
            title=c.name,
            severity="medium",
            frequency=c.frequency,
            examples=list(c.session_ids[:3]),
            symptom=c.description,
            proposed_fix=(
                "Кластер сессий с похожим pattern. Изучите примеры выше и "
                "проверьте, нужна ли правка в CLAUDE.md / hook / skill."
            ),
            evidence_quotes=[],
            mast_taxonomy=None,
        )
