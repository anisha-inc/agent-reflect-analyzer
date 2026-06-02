"""Tests for analyzer.identity — must match bash shipper's sha256→16 hex output."""

from __future__ import annotations

import hashlib
import subprocess
from unittest.mock import patch

from analyzer import identity


def _expected(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def test_dev_id_matches_bash_shipper():
    with patch.object(subprocess, "check_output", return_value="alice@example.com\n"):
        assert identity.dev_id() == _expected("alice@example.com")


def test_proj_id_uses_origin_url():
    def fake_co(cmd, **kw):
        if cmd[:2] == ["git", "remote"]:
            return "git@github.com:org/repo.git\n"
        return ""
    with patch.object(subprocess, "check_output", side_effect=fake_co):
        assert identity.proj_id() == _expected("git@github.com:org/repo.git")


def test_proj_id_falls_back_to_cwd_when_no_origin():
    def fake_co(cmd, **kw):
        if cmd[:2] == ["git", "remote"]:
            raise subprocess.CalledProcessError(128, cmd)
        return ""
    with patch.object(subprocess, "check_output", side_effect=fake_co):
        result = identity.proj_id()
        assert len(result) == 16
        # Should be hex.
        int(result, 16)


def test_dev_id_strips_trailing_whitespace():
    """Matches `printf '%s'` behavior in ship.sh — no trailing newline factored in."""
    with patch.object(subprocess, "check_output", return_value="bob@example.com\n  "):
        assert identity.dev_id() == _expected("bob@example.com")
