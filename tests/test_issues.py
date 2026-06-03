"""Tests for analyzer.issues — body rendering + gh issue create invocation."""

from __future__ import annotations

from unittest.mock import patch

from analyzer import issues
from analyzer.llm.schemas import Candidate


def _cand() -> Candidate:
    return Candidate(
        source="opus_top_k",
        pattern_id="bash-loop",
        title="Bash hook retries the same compound command",
        severity="medium",
        frequency=4,
        examples=["sess-A", "sess-B"],
        symptom="Agent re-issues `&&`-chained commands and gets BASH-001.",
        proposed_fix="Add a hint in CLAUDE.md describing the hook.",
        evidence_quotes=["BASH-001: Compound operators forbidden"],
        mast_taxonomy="SI-1.3",
    )


def test_render_body_contains_all_sections():
    body = issues.render_for_preview(_cand())
    assert "## Симптом" in body
    assert "## Fix" in body
    assert "## Examples" in body
    assert "## /start-task" in body
    assert "bash-loop" in body
    assert "BASH-001" in body
    assert "`sess-A`" in body
    assert "SI-1.3" in body


def test_render_body_handles_empty_evidence_and_examples():
    c = _cand()
    c.evidence_quotes = []
    c.examples = []
    body = issues.render_for_preview(c)
    assert "## Examples" in body


def test_emit_issue_dry_run_does_not_shell_out():
    with patch.object(issues, "run_external") as mocked:
        url = issues.emit_issue(_cand(), repo="octo-org/octo-repo", dry_run=True)
        assert url is None
        mocked.assert_not_called()


def test_emit_issue_calls_gh_with_body_file(tmp_path):
    fake_url = "https://github.com/octo-org/octo-repo/issues/123\n"
    with patch.object(issues, "run_external", return_value=fake_url) as mocked:
        url = issues.emit_issue(
            _cand(),
            repo="octo-org/octo-repo",
            token="ghs_dummy",
            dry_run=False,
        )
        assert url == fake_url.strip()
        # Most recent call is `gh issue create` (label-create runs first when uncached).
        args = mocked.call_args.args[0]
        assert args[0] == "gh"
        assert "--repo" in args
        assert args[args.index("--repo") + 1] == "octo-org/octo-repo"
        assert "--label" in args
        assert "--body-file" in args


def test_emit_issue_resolves_token_when_none():
    fake_url = "https://github.com/octo-org/octo-repo/issues/9\n"
    with (
        patch.object(issues.auth, "resolve_github_token", return_value="ghs_resolved") as res,
        patch.object(issues, "run_external", return_value=fake_url),
    ):
        url = issues.emit_issue(_cand(), repo="octo-org/octo-repo", dry_run=False)
    assert url == fake_url.strip()
    res.assert_called_once()


def test_emit_issue_raises_without_any_token():
    with patch.object(issues.auth, "resolve_github_token", return_value=None):
        try:
            issues.emit_issue(_cand(), repo="octo-org/octo-repo", dry_run=False)
        except RuntimeError as e:
            assert "no GitHub token available" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_emit_issue_propagates_gh_failure():
    with patch.object(issues, "run_external", side_effect=RuntimeError("rate limit")):
        try:
            issues.emit_issue(_cand(), repo="octo-org/octo-repo", token="ghs_dummy")
        except RuntimeError as e:
            assert "gh issue create failed" in str(e)
        else:
            raise AssertionError("expected RuntimeError")
