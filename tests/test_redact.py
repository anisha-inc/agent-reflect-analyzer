"""Tests for analyzer.redact — secrets out, code identifiers untouched."""

from __future__ import annotations

from analyzer import audit, redact
from analyzer.llm.schemas import Candidate


def test_redact_anthropic_key_removed():
    text = "Found leak: sk-ant-api03-aBcDeFGHijklMNOpqrstuvwxYZ1234567 in logs."
    out = redact.redact_string(text)
    assert "sk-ant-api03" not in out


def test_redact_gh_pat_removed():
    text = "Token ghp_aBcDeFGHijklmnopqrstuvwxyz123456 stolen!"
    out = redact.redact_string(text)
    assert "ghp_aBcDeFGHijklmnopqrstuvwxyz" not in out


def test_redact_aws_key_removed():
    text = "AKIAIOSFODNN7EXAMPLE in source"
    out = redact.redact_string(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in out


def test_redact_jwt_removed():
    jwt = (
        "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxIiwiaWF0IjoxNzEyMzQ1Njc4fQ."
        "abCDef1234_-ABCdef5678_-XYZabcXYZabcXYZ"
    )
    text = f"Bearer {jwt}"
    out = redact.redact_string(text)
    assert jwt not in out


def test_redact_email_removed():
    text = "Contact alice@example.com about this."
    out = redact.redact_string(text)
    assert "alice@example.com" not in out


def test_redact_does_not_touch_code_identifiers():
    """Variable names + camelCase should NOT be redacted (no general entities enabled)."""
    text = "Variable userName had value None; method fooBar() returned 42."
    out = redact.redact_string(text)
    assert "userName" in out
    assert "fooBar" in out


def test_redact_candidate_updates_all_text_fields():
    c = Candidate(
        source="opus_top_k",
        pattern_id="leak",
        title="Leak found: ghp_aBcDeFGHijklmnopqrstuvwxyz123456",
        symptom="Saw email leak@example.com inadvertently",
        proposed_fix="Don't log keys",
        evidence_quotes=["found sk-ant-api03-aBcDeFGHijklMNOpqrstuvwxYZ1234567"],
    )
    record = audit.RunRecord()
    redact.redact_candidate(c, record=record)
    assert "ghp_aBcDeFGHijklmnopqrstuvwxyz" not in c.title
    assert "leak@example.com" not in c.symptom
    assert "sk-ant-api03" not in c.evidence_quotes[0]
    # Counter records redacted entity types.
    assert sum(record.redacted.values()) >= 3


def test_redact_counter_tracks_per_entity():
    record = audit.RunRecord()
    text = (
        "Two emails: a@example.com b@example.com; "
        "key sk-ant-api03-aBcDeFGHijklMNOpqrstuvwxYZ1234567"
    )
    redact.redact_string(text, record=record)
    # At least one ANTHROPIC_KEY + email_address detections recorded.
    assert record.redacted.get("ANTHROPIC_KEY", 0) >= 1
    assert record.redacted.get("EMAIL_ADDRESS", 0) >= 1
