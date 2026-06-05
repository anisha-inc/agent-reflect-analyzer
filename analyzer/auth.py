"""GitHub token resolution + 1Password secret reads for the analyzer.

The GitHub token comes from the ambient environment (``GH_TOKEN``/``GITHUB_TOKEN``)
— set by the caller's CI workflow (``github.token``) or the developer's shell.
1P reads (``_op_read``) cover the Anthropic API key and the ``claude -p`` OAuth
token, gated on ``OP_SVC_TOKEN``.
"""

from __future__ import annotations

import os

from pydantic import ValidationError

from . import config
from .config import Settings
from .subprocess_util import run_external


def _op_read(ref: str) -> str | None:
    """Read a 1P secret reference. Returns None on any failure."""
    token = os.environ.get("OP_SVC_TOKEN")
    if not token:
        return None
    env = {**os.environ, "OP_SERVICE_ACCOUNT_TOKEN": token}
    try:
        out = run_external(["op", "read", ref], timeout=10, env=env, redact_argv_log=True).strip()
        return out or None
    except RuntimeError:
        return None


def _settings_or_none(settings: Settings | None) -> Settings | None:
    if settings is not None:
        return settings
    try:
        return config.load_settings()
    except ValidationError:
        return None


def read_oauth_token(settings: Settings | None = None) -> str | None:
    """Long-life OAuth token for `claude -p` subscription billing. Read from 1P.

    Tries each candidate ref in order and returns the first non-empty value.
    Returns None when configuration is missing or no ref resolves.
    """
    settings = _settings_or_none(settings)
    if settings is None:
        return None
    for ref in settings.oauth_token_refs:
        val = _op_read(ref)
        if val:
            return val
    return None


def read_anthropic_api_key(settings: Settings | None = None) -> str | None:
    """API key for AsyncAnthropic (Stages [4]/[5] Haiku). Read from env or 1P."""
    val = os.environ.get("ANTHROPIC_API_KEY")
    if val:
        return val
    settings = _settings_or_none(settings)
    if settings is None:
        return None
    return _op_read(settings.anthropic_key_ref)


def resolve_github_token() -> str | None:
    # No App minting: the GitHub identity is whoever owns the ambient token
    # (CI → github-actions[bot]; locally → the dev's gh auth token).
    return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
