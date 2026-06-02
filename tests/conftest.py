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
