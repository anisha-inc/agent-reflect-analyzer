"""Mint a GitHub installation token via the vendored github-app-token script.

The vendored script (``scripts/github-app-token``) prints the token to stdout.
Per-repo / per-permission scoping is NOT available in the upstream script — the
token follows the GitHub App's configured permissions (issues:write).

If ``ANISHA_OP_SVC_TOKEN`` isn't in the environment, ``mint_github_token``
raises — the caller catches it and surfaces an actionable message.
"""

from __future__ import annotations

import os
import pathlib
import subprocess

from pydantic import ValidationError

from . import config
from .config import Settings


def _op_read(ref: str) -> str | None:
    """Read a 1P secret reference. Returns None on any failure."""
    token = os.environ.get("ANISHA_OP_SVC_TOKEN")
    if not token:
        return None
    env = {**os.environ, "OP_SERVICE_ACCOUNT_TOKEN": token}
    try:
        out = subprocess.check_output(
            ["op", "read", ref], env=env, text=True,
            stderr=subprocess.DEVNULL, timeout=10,
        ).strip()
        return out or None
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
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


def mint_github_token(*, target_org: str, timeout_s: int = 30) -> str:
    """Return an installation token for ``target_org``. Raises on failure."""
    if "ANISHA_OP_SVC_TOKEN" not in os.environ:
        raise RuntimeError(
            "ANISHA_OP_SVC_TOKEN not in env — cannot mint GitHub App token."
        )
    script = _script_path()
    if not script.exists():
        raise RuntimeError(f"vendored github-app-token not found at {script}")
    env = {**os.environ, "GH_APP_TARGET_ORG": target_org}
    try:
        out = subprocess.check_output(
            [str(script)], env=env, text=True, timeout=timeout_s,
            stderr=subprocess.PIPE,
        ).strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"github-app-token failed: exit={e.returncode} stderr={(e.stderr or '')[:200]}"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"github-app-token timed out after {timeout_s}s") from e
    if not out:
        raise RuntimeError("github-app-token returned empty stdout.")
    return out
