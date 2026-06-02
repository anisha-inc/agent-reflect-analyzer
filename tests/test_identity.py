"""Tests for analyzer.identity — must match bash shipper's sha256→16 hex output."""

from __future__ import annotations

import hashlib
from unittest.mock import patch

from analyzer import identity


def _expected(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def test_dev_id_matches_bash_shipper():
    with patch.object(identity, "run_external", return_value="alice@example.com\n"):
        assert identity.dev_id() == _expected("alice@example.com")


def test_proj_id_uses_origin_url():
    with patch.object(identity, "run_external", return_value="git@github.com:org/repo.git\n"):
        assert identity.proj_id() == _expected("git@github.com:org/repo.git")


def test_proj_id_falls_back_to_cwd_when_no_origin():
    with patch.object(identity, "run_external", side_effect=RuntimeError("no origin")):
        result = identity.proj_id()
        assert len(result) == 16
        int(result, 16)  # must be hex


def test_dev_id_strips_trailing_whitespace():
    """Matches `printf '%s'` behavior in ship.sh — no trailing newline factored in."""
    with patch.object(identity, "run_external", return_value="bob@example.com\n  "):
        assert identity.dev_id() == _expected("bob@example.com")
