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
        # Self-contained email regex — we deliberately do NOT use presidio's
        # EmailRecognizer, which validates the TLD via tldextract (an HTTP fetch
        # of the public-suffix list that the no-network test lockdown blocks).
        PatternRecognizer(
            supported_entity="EMAIL_ADDRESS",
            patterns=[Pattern("email", r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", 0.9)],
        ),
    ]


@functools.lru_cache(maxsize=1)
def _engine() -> tuple[Any, Any]:
    """Build (recognizers, anonymizer) once.

    We run the recognizers directly rather than via AnalyzerEngine: every entity
    we care about is matched by a pure-regex recognizer, none of which need NLP
    artifacts or network. This avoids requiring a spaCy model at runtime —
    AnalyzerEngine() would otherwise try to load `en_core_web_lg` and fail where
    no model is installed (e.g. CI).
    """
    from presidio_anonymizer import AnonymizerEngine

    return _custom_recognizers(), AnonymizerEngine()


def redact_string(text: str, *, record: audit.RunRecord | None = None) -> str:
    if not text:
        return text
    try:
        recognizers, anonymizer = _engine()
    except Exception:
        return text  # presidio unavailable — leave as-is (acceptable fail-open).

    results = []
    for rec in recognizers:
        results.extend(
            rec.analyze(text=text, entities=rec.supported_entities, nlp_artifacts=None) or []
        )
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
