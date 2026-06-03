"""Tests for analyzer.cli — --check path + flag parsing."""

from __future__ import annotations

import json
from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner

from analyzer import cli


def test_help_lists_all_flags():
    result = CliRunner().invoke(cli.main, ["--help"])
    assert result.exit_code == 0
    for flag in (
        "--check",
        "--since",
        "--limit",
        "--repo",
        "--emit-issues",
        "--top-k",
        "--strategy",
        "--cluster",
        "--include-closed-since",
        "--api-key-fallback",
        "--json",
        "--verbose",
    ):
        assert flag in result.output, f"--help missing {flag}"


def test_check_json_returns_8_probes():
    fake = [
        {"id": "p1", "category": "env", "ok": True, "detail": "ok"},
    ] * 8
    with patch.object(cli.checks, "run_all", return_value=fake):
        result = CliRunner().invoke(cli.main, ["--check", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 8


def test_check_human_exits_nonzero_on_failure():
    fake = [
        {"id": "p1", "category": "env", "ok": False, "detail": "missing"},
    ]
    with patch.object(cli.checks, "run_all", return_value=fake):
        result = CliRunner().invoke(cli.main, ["--check"])
    assert result.exit_code == 1
    assert "FAIL" in result.output


def test_check_human_exits_zero_when_all_pass():
    fake = [
        {"id": "p1", "category": "env", "ok": True, "detail": "ok"},
    ]
    with patch.object(cli.checks, "run_all", return_value=fake):
        result = CliRunner().invoke(cli.main, ["--check"])
    assert result.exit_code == 0
    assert "OK" in result.output


def test_resolve_read_owner_from_repo_lowercased():
    assert cli._resolve_read_owner("Qonversion/Dash-Mono") == "qonversion"


def test_resolve_read_owner_from_default_org(monkeypatch):
    class _S:
        target_org_default = "Anisha-Inc"

    monkeypatch.setattr(cli.config, "load_settings", lambda: _S())
    assert cli._resolve_read_owner(None) == "anisha-inc"


def test_resolve_read_owner_fail_closed_without_org(monkeypatch):
    class _S:
        target_org_default = None

    monkeypatch.setattr(cli.config, "load_settings", lambda: _S())
    with pytest.raises(click.UsageError):
        cli._resolve_read_owner(None)


def test_resolve_read_owner_rejects_injection_charset():
    # owner segment contains shell/SQL metacharacters → must be rejected before
    # it can reach the interpolated read glob.
    with pytest.raises(click.UsageError):
        cli._resolve_read_owner("foo';DROP/bar")


def test_summary_table_renders_known_keys():
    table = cli._summary_table(
        {
            "sessions_analyzed": 5,
            "candidates_total": 3,
            "candidates_after_dedup": 2,
            "candidates_after_redact": 2,
            "issues_emitted": 1,
            "issue_urls": ["https://github.com/a/b/issues/1"],
            "total_wall_s": 12.3,
            "est_cost_usd": 0.05,
            "audit_log": "/tmp/foo",
        }
    )
    assert "sessions analyzed" in table
    assert "5" in table
    assert "/tmp/foo" in table
