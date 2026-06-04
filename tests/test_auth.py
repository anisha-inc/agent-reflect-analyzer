"""Tests for analyzer.auth — ambient GitHub token resolution."""

from __future__ import annotations

from analyzer import auth


def test_resolve_prefers_gh_token(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ambient-gh")
    monkeypatch.setenv("GITHUB_TOKEN", "ambient-actions")
    assert auth.resolve_github_token() == "ambient-gh"


def test_resolve_falls_back_to_github_token(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "ambient-actions")
    assert auth.resolve_github_token() == "ambient-actions"


def test_resolve_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert auth.resolve_github_token() is None
