"""Mint a GitHub installation token via the vendored github-app-token script.

The vendored script (see agent-reflect/scripts/github-app-token) prints the
token to stdout. Per-repo / per-permission scoping is NOT available in the
upstream script — token follows the GitHub App's configured permissions
(anisha-ci is configured with issues:write per atlas).

If `ANISHA_OP_SVC_TOKEN` isn't in env, mint() raises — the skill catches and
surfaces an actionable message.
"""

from __future__ import annotations

import os
import pathlib
import subprocess

from . import config


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


def read_oauth_token() -> str | None:
    """Long-life OAuth token for `claude -p` subscription billing. Read from 1P.

    Tries each candidate ref in order — supports rename transition where the
    new label `CLAUDE_CODE_OAUTH_TOKEN` may not yet be the only one. Returns
    first non-empty value.
    """
    for ref in config.OAUTH_TOKEN_REFS:
        val = _op_read(ref)
        if val:
            return val
    return None


def read_anthropic_api_key() -> str | None:
    """API key for AsyncAnthropic (Stages [4]/[5] Haiku). Read from env or 1P."""
    val = os.environ.get("ANTHROPIC_API_KEY")
    if val:
        return val
    return _op_read(config.ANTHROPIC_KEY_REF)


def _script_path() -> pathlib.Path:
    """Return path to the vendored github-app-token script.

    Plugin layout:
        agent-reflect/
          scripts/github-app-token        ← target
          lib/analyzer/analyzer/auth.py   ← __file__
    """
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        return pathlib.Path(plugin_root) / "scripts" / "github-app-token"
    # Fallback for dev runs (no env): __file__ is 4 levels deep under agent-reflect/.
    here = pathlib.Path(__file__).resolve()
    return here.parent.parent.parent.parent / "scripts" / "github-app-token"


def mint_github_token(*, target_org: str = "anisha-inc", timeout_s: int = 30) -> str:
    """Return an installation token. Raises RuntimeError on failure."""
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
