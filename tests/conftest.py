"""Shared pytest fixtures and import-path setup.

Adds the parent dir to sys.path so tests can import the `analyzer` package
without an installed editable wheel — useful for fast local iteration and CI
where uv sync may not have completed yet.
"""

from __future__ import annotations

import os
import sys

import pytest

THIS_DIR = os.path.dirname(__file__)
PKG_PARENT = os.path.abspath(os.path.join(THIS_DIR, ".."))
if PKG_PARENT not in sys.path:
    sys.path.insert(0, PKG_PARENT)


@pytest.fixture(autouse=True)
def _isolated_audit_dir(tmp_path, monkeypatch):
    """Redirect audit writes to a tmp dir so tests don't pollute ~/.local/state."""
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
    # config.AUDIT_DIR was computed at import — patch it for the run.
    from analyzer import config

    monkeypatch.setattr(config, "PLUGIN_DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "AUDIT_DIR", tmp_path / "audit")
    yield


@pytest.fixture(autouse=True)
def _default_settings_env(monkeypatch):
    """Supply dummy AGENT_REFLECT_* config so ``config.load_settings()`` succeeds
    in tests. Tests that exercise the missing/invalid-config path clear or
    override these explicitly via their own ``monkeypatch``."""
    monkeypatch.setenv("AGENT_REFLECT_GCS_BUCKET", "gs://test-bucket")
    monkeypatch.setenv("AGENT_REFLECT_HMAC_AKID_REF", "op://TEST/hmac/akid")
    monkeypatch.setenv("AGENT_REFLECT_HMAC_SECRET_REF", "op://TEST/hmac/secret")
    monkeypatch.setenv("AGENT_REFLECT_ANTHROPIC_KEY_REF", "op://TEST/anthropic/key")
    monkeypatch.setenv("AGENT_REFLECT_OAUTH_TOKEN_REF", "op://TEST/oauth/token")
    monkeypatch.delenv("AGENT_REFLECT_TARGET_ORG_DEFAULT", raising=False)
    yield
