"""Tests for analyzer.auth — mint_github_token shells out to vendored script."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from analyzer import auth


def test_mint_raises_without_op_token(monkeypatch):
    monkeypatch.delenv("ANISHA_OP_SVC_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="ANISHA_OP_SVC_TOKEN"):
        auth.mint_github_token(target_org="octo")


def test_mint_returns_token_on_success(monkeypatch):
    monkeypatch.setenv("ANISHA_OP_SVC_TOKEN", "dummy")
    with (
        patch.object(auth, "_script_path") as sp,
        patch.object(auth, "run_external", return_value="ghs_abc123\n"),
    ):
        sp.return_value.exists.return_value = True
        token = auth.mint_github_token(target_org="octo")
    assert token == "ghs_abc123"


def test_mint_raises_on_script_failure(monkeypatch):
    monkeypatch.setenv("ANISHA_OP_SVC_TOKEN", "dummy")
    with (
        patch.object(auth, "_script_path") as sp,
        patch.object(auth, "run_external", side_effect=RuntimeError("boom")),
    ):
        sp.return_value.exists.return_value = True
        with pytest.raises(RuntimeError, match="github-app-token failed"):
            auth.mint_github_token(target_org="octo")


def test_mint_raises_on_empty_stdout(monkeypatch):
    monkeypatch.setenv("ANISHA_OP_SVC_TOKEN", "dummy")
    with (
        patch.object(auth, "_script_path") as sp,
        patch.object(auth, "run_external", return_value="   \n"),
    ):
        sp.return_value.exists.return_value = True
        with pytest.raises(RuntimeError, match="empty stdout"):
            auth.mint_github_token(target_org="octo")
