"""Tests for analyzer.dedup — parse + fallback dedup."""

from __future__ import annotations

from unittest.mock import patch

from analyzer import dedup
from analyzer.llm.schemas import Candidate


def _cand(pid: str, title: str, symptom: str) -> Candidate:
    return Candidate(
        source="opus_top_k",
        pattern_id=pid,
        title=title,
        symptom=symptom,
        proposed_fix="fix",
    )


def test_parse_issue_sections_extracts_symptom_and_fix():
    body = "## Симптом\nAgent ignores hook.\n\n## Fix\nRewrite hook.\n\n## Examples"
    sec = dedup.parse_issue_sections(body)
    assert "Agent ignores hook" in sec["symptom"]
    assert "Rewrite hook" in sec["fix"]


def test_parse_issue_sections_handles_missing_sections():
    sec = dedup.parse_issue_sections("just a body")
    assert sec == {"symptom": "", "fix": ""}


def test_dedup_empty_inputs_passthrough():
    assert dedup.dedup_candidates([], []) == []
    candidates = [_cand("x", "Foo", "sym")]
    assert dedup.dedup_candidates(candidates, []) == candidates


def test_dedup_fallback_drops_obvious_duplicate():
    candidates = [
        _cand("bash-loop", "Bash loop", "Agent loops on bash"),
        _cand("read-thrash", "Read Edit thrash", "Agent re-reads"),
    ]
    existing = [
        {"title": "Bash loop already filed", "body": "## Симптом\nAgent loops on bash"},
    ]
    kept = dedup.dedup_candidates(candidates, existing, force_fallback=True)
    pids = {c.pattern_id for c in kept}
    assert pids == {"read-thrash"}


def test_dedup_fallback_drops_when_pattern_id_in_title():
    candidates = [_cand("bash-001", "Some title", "sym")]
    existing = [{"title": "Patch for bash-001 already shipped", "body": ""}]
    kept = dedup.dedup_candidates(candidates, existing, force_fallback=True)
    assert kept == []


def test_dedup_fallback_drops_when_two_tokens_overlap():
    candidates = [_cand("x", "Hook violates plugin contract sometimes", "sym")]
    existing = [{"title": "Plugin contract violation", "body": ""}]
    kept = dedup.dedup_candidates(candidates, existing, force_fallback=True)
    # "plugin" + "contract" overlap (>3 chars each) — dropped.
    assert kept == []


def test_dedup_fallback_keeps_unrelated():
    candidates = [_cand("totally-new", "Totally novel pattern", "novel issue")]
    existing = [{"title": "Something completely else", "body": "## Симптом\nDifferent."}]
    kept = dedup.dedup_candidates(candidates, existing, force_fallback=True)
    assert len(kept) == 1


def test_fetch_open_issues_uses_resolved_token():
    """PF-29: fetch_open_issues threads the resolved GitHub token into the
    `gh issue list` subprocess env (caller token preferred over minting)."""
    captured: dict = {}

    def _fake_run(argv, **kwargs):
        captured["env"] = kwargs.get("env", {})
        return "[]"

    with (
        patch.object(dedup, "run_external", side_effect=_fake_run),
        patch("analyzer.auth.resolve_github_token", return_value="resolved-tok") as res,
    ):
        out = dedup.fetch_open_issues("octo-org/octo-repo")
    assert out == []
    res.assert_called_once()
    assert captured["env"].get("GH_TOKEN") == "resolved-tok"
