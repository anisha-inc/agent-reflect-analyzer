"""Presidio-based PII redaction of candidate fields.

Custom recognizers cover the secrets we actually emit in agent logs:
Anthropic keys, GitHub PATs, AWS access keys, GCS HMAC, JWTs. EMAIL_ADDRESS
is also enabled. We deliberately do NOT enable general PERSON / US_DRIVER /
PHONE_NUMBER recognizers — they produce false-positives on code identifiers
(variable names, table names) per plan R5.
"""

from __future__ import annotations

import functools
from typing import Any

from . import audit
from .llm.schemas import Candidate


def _custom_recognizers():
    from presidio_analyzer import Pattern, PatternRecognizer

    return [
        PatternRecognizer(
            supported_entity="ANTHROPIC_KEY",
            patterns=[Pattern("sk-ant-*", r"sk-ant-[a-zA-Z0-9-_]{30,}", 0.95)],
        ),
        PatternRecognizer(
            supported_entity="GH_PAT",
            patterns=[
                Pattern("ghp/gh_pat", r"(ghp|gh_pat|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}", 0.95)
            ],
        ),
        PatternRecognizer(
            supported_entity="AWS_KEY", patterns=[Pattern("aws", r"AKIA[A-Z0-9]{16}", 0.95)]
        ),
        PatternRecognizer(
            supported_entity="GCS_HMAC", patterns=[Pattern("hmac", r"GOOG1E[A-Z0-9]{56,}", 0.95)]
        ),
        PatternRecognizer(
            supported_entity="JWT",
            patterns=[Pattern("jwt", r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", 0.9)],
        ),
    ]


_ENTITIES = ["ANTHROPIC_KEY", "GH_PAT", "AWS_KEY", "GCS_HMAC", "JWT", "EMAIL_ADDRESS"]


@functools.lru_cache(maxsize=1)
def _engine() -> tuple[Any, Any]:
    """Build (analyzer, anonymizer) once."""
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine

    analyzer = AnalyzerEngine()
    for r in _custom_recognizers():
        analyzer.registry.add_recognizer(r)
    return analyzer, AnonymizerEngine()


def redact_string(text: str, *, record: audit.RunRecord | None = None) -> str:
    if not text:
        return text
    try:
        analyzer, anonymizer = _engine()
    except Exception:
        return text  # presidio unavailable — leave as-is (acceptable fail-open).

    results = analyzer.analyze(text=text, entities=_ENTITIES, language="en")
    if not results:
        return text

    if record is not None:
        for r in results:
            record.redacted[r.entity_type] = record.redacted.get(r.entity_type, 0) + 1

    return anonymizer.anonymize(text=text, analyzer_results=results).text


def redact_candidate(c: Candidate, *, record: audit.RunRecord | None = None) -> Candidate:
    c.symptom = redact_string(c.symptom, record=record)
    c.proposed_fix = redact_string(c.proposed_fix, record=record)
    c.title = redact_string(c.title, record=record)
    c.evidence_quotes = [redact_string(q, record=record) for q in c.evidence_quotes]
    return c
