"""Tests for analyzer.config.Settings — strict, no-default env loading."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from analyzer import config

_REQUIRED = [
    "AGENT_REFLECT_GCS_BUCKET",
    "AGENT_REFLECT_HMAC_AKID",
    "AGENT_REFLECT_HMAC_SECRET",
]


def test_settings_loads_from_env():
    s = config.load_settings()
    assert s.gcs_bucket == "gs://test-bucket"
    assert s.hmac_akid == "x" * 60
    assert s.hmac_secret == "y" * 60
    assert s.target_org_default is None


def test_settings_requires_all_envs(monkeypatch):
    for var in _REQUIRED:
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ValidationError):
        config.load_settings()


@pytest.mark.parametrize("var", _REQUIRED)
def test_settings_missing_single_var_raises(monkeypatch, var):
    monkeypatch.delenv(var, raising=False)
    with pytest.raises(ValidationError):
        config.load_settings()


def test_target_org_default_optional(monkeypatch):
    monkeypatch.setenv("AGENT_REFLECT_TARGET_ORG_DEFAULT", "octo-org")
    s = config.load_settings()
    assert s.target_org_default == "octo-org"
