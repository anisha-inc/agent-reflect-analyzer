"""Tests for analyzer.issues — body rendering + gh issue create invocation."""

from __future__ import annotations

import subprocess
from unittest.mock import patch, MagicMock

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
    with patch("subprocess.check_output") as mocked:
        url = issues.emit_issue(_cand(), repo="anisha-inc/plugins", dry_run=True)
        assert url is None
        mocked.assert_not_called()


def test_emit_issue_calls_gh_with_body_file(tmp_path):
    fake_url = "https://github.com/anisha-inc/plugins/issues/123\n"
    with patch("subprocess.check_output", return_value=fake_url) as mocked:
        url = issues.emit_issue(
            _cand(), repo="anisha-inc/plugins", token="ghs_dummy", dry_run=False,
        )
        assert url == fake_url.strip()
        args = mocked.call_args.args[0]
        assert args[0] == "gh"
        assert "--repo" in args
        assert args[args.index("--repo") + 1] == "anisha-inc/plugins"
        assert "--label" in args
        assert "--body-file" in args


def test_emit_issue_propagates_gh_failure():
    err = subprocess.CalledProcessError(1, "gh", output="rate limit")
    with patch("subprocess.check_output", side_effect=err):
        try:
            issues.emit_issue(_cand(), repo="anisha-inc/plugins", token="ghs_dummy")
        except RuntimeError as e:
            assert "gh issue create failed" in str(e)
        else:
            raise AssertionError("expected RuntimeError")
