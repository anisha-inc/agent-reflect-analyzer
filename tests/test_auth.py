"""Tests for analyzer.auth — mint_github_token shells out to vendored script."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from analyzer import auth


def test_mint_raises_without_op_token(monkeypatch):
    monkeypatch.delenv("OP_SVC_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="OP_SVC_TOKEN"):
        auth.mint_github_token(target_org="octo")


def test_mint_returns_token_on_success(monkeypatch):
    monkeypatch.setenv("OP_SVC_TOKEN", "dummy")
    with (
        patch.object(auth, "_script_path") as sp,
        patch.object(auth, "run_external", return_value="ghs_abc123\n"),
    ):
        sp.return_value.exists.return_value = True
        token = auth.mint_github_token(target_org="octo")
    assert token == "ghs_abc123"


def test_mint_raises_on_script_failure(monkeypatch):
    monkeypatch.setenv("OP_SVC_TOKEN", "dummy")
    with (
        patch.object(auth, "_script_path") as sp,
        patch.object(auth, "run_external", side_effect=RuntimeError("boom")),
    ):
        sp.return_value.exists.return_value = True
        with pytest.raises(RuntimeError, match="github-app-token failed"):
            auth.mint_github_token(target_org="octo")


def test_mint_raises_on_empty_stdout(monkeypatch):
    monkeypatch.setenv("OP_SVC_TOKEN", "dummy")
    with (
        patch.object(auth, "_script_path") as sp,
        patch.object(auth, "run_external", return_value="   \n"),
    ):
        sp.return_value.exists.return_value = True
        with pytest.raises(RuntimeError, match="empty stdout"):
            auth.mint_github_token(target_org="octo")


def test_resolve_prefers_ambient_gh_token(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ambient-gh")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    # Ambient token present → mint must NOT be called (PF-29).
    with patch.object(auth, "mint_github_token", side_effect=AssertionError("mint called")):
        assert auth.resolve_github_token(target_org="octo") == "ambient-gh"


def test_resolve_prefers_ambient_github_token(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "ambient-actions")
    with patch.object(auth, "mint_github_token", side_effect=AssertionError("mint called")):
        assert auth.resolve_github_token(target_org="octo") == "ambient-actions"


def test_resolve_falls_back_to_mint(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with patch.object(auth, "mint_github_token", return_value="ghs_minted"):
        assert auth.resolve_github_token(target_org="octo") == "ghs_minted"


def test_resolve_returns_none_when_mint_fails(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with patch.object(auth, "mint_github_token", side_effect=RuntimeError("no op token")):
        assert auth.resolve_github_token(target_org="octo") is None


def test_script_path_resolves_to_existing_script(monkeypatch):
    # Source checkout: candidate 3 (repo-root scripts/github-app-token) exists.
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    p = auth._script_path()
    assert p.name == "github-app-token"
    assert p.exists()
