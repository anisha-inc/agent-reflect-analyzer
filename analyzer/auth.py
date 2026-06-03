"""Mint a GitHub installation token via the vendored github-app-token script.

The vendored script (``scripts/github-app-token``) prints the token to stdout.
Per-repo / per-permission scoping is NOT available in the upstream script — the
token follows the GitHub App's configured permissions (issues:write).

If ``OP_SVC_TOKEN`` isn't in the environment, ``mint_github_token``
raises — the caller catches it and surfaces an actionable message.
"""

from __future__ import annotations

import os
import pathlib

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


def _script_path() -> pathlib.Path:
    """Return path to the vendored github-app-token script.

    Repo layout:
        scripts/github-app-token        ← target
        analyzer/auth.py                ← __file__
    """
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        return pathlib.Path(plugin_root) / "scripts" / "github-app-token"
    # Fallback for source checkouts: __file__ is analyzer/auth.py at repo root.
    here = pathlib.Path(__file__).resolve()
    return here.parent.parent / "scripts" / "github-app-token"


def resolve_github_token(*, target_org: str) -> str | None:
    """Resolve a GitHub token, preferring a caller-provided ambient token over
    minting an org-scoped App token (PF-29).

    Server-side, the reusable workflow exports the caller repo's own
    ``GH_TOKEN``/``GITHUB_TOKEN`` (``github.token``) — which can read/write that
    org's private repos. Minting the analyzer's own App token first would shadow
    that correct token and break cross-org dedup/emit (the App isn't installed
    on the caller org). So: ambient token wins; mint only as a fallback when no
    ambient token is present. Returns None when neither source is available.
    """
    ambient = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if ambient:
        return ambient
    try:
        return mint_github_token(target_org=target_org)
    except RuntimeError:
        return None


def mint_github_token(*, target_org: str, timeout_s: int = 30) -> str:
    """Return an installation token for ``target_org``. Raises on failure."""
    if "OP_SVC_TOKEN" not in os.environ:
        raise RuntimeError("OP_SVC_TOKEN not in env — cannot mint GitHub App token.")
    script = _script_path()
    if not script.exists():
        raise RuntimeError(f"vendored github-app-token not found at {script}")
    env = {**os.environ, "GH_APP_TARGET_ORG": target_org}
    try:
        out = run_external([str(script)], timeout=timeout_s, env=env).strip()
    except RuntimeError as e:
        raise RuntimeError(f"github-app-token failed: {e}") from e
    if not out:
        raise RuntimeError("github-app-token returned empty stdout.")
    return out
