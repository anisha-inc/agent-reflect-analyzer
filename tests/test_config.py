"""Tests for analyzer.config.Settings — strict, no-default env loading."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from analyzer import config

_REQUIRED = [
    "AGENT_REFLECT_GCS_BUCKET",
    "AGENT_REFLECT_HMAC_AKID_REF",
    "AGENT_REFLECT_HMAC_SECRET_REF",
    "AGENT_REFLECT_ANTHROPIC_KEY_REF",
    "AGENT_REFLECT_OAUTH_TOKEN_REF",
]


def test_settings_loads_from_env():
    s = config.load_settings()
    assert s.gcs_bucket == "gs://test-bucket"
    assert s.hmac_akid_ref == "op://TEST/hmac/akid"
    assert s.oauth_token_refs == ["op://TEST/oauth/token"]
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


def test_oauth_refs_split_on_comma(monkeypatch):
    monkeypatch.setenv("AGENT_REFLECT_OAUTH_TOKEN_REF", "op://a/x,op://b/y")
    s = config.load_settings()
    assert s.oauth_token_refs == ["op://a/x", "op://b/y"]


def test_oauth_single_ref_is_one_element_list(monkeypatch):
    monkeypatch.setenv("AGENT_REFLECT_OAUTH_TOKEN_REF", "op://only/one")
    s = config.load_settings()
    assert s.oauth_token_refs == ["op://only/one"]


def test_oauth_empty_string_is_validation_error(monkeypatch):
    # Defense-in-depth: an explicitly empty value must raise, not yield [].
    monkeypatch.setenv("AGENT_REFLECT_OAUTH_TOKEN_REF", "")
    with pytest.raises(ValidationError):
        config.load_settings()


def test_target_org_default_optional(monkeypatch):
    monkeypatch.setenv("AGENT_REFLECT_TARGET_ORG_DEFAULT", "octo-org")
    s = config.load_settings()
    assert s.target_org_default == "octo-org"
