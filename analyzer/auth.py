"""GitHub token + LLM credential resolution for the analyzer.

All three credentials come straight from the ambient environment — the analyzer
never reaches out to 1Password. Secret resolution (``op read`` /
``load-secrets-action``) happens upstream, in the caller's CI workflow or the
developer's credential-sync step. Here we only read already-resolved env vars.
"""

from __future__ import annotations

import os


def read_oauth_token() -> str | None:
    """Long-life OAuth token for ``claude -p`` subscription billing.

    Native ``CLAUDE_CODE_OAUTH_TOKEN`` env var — the ``claude`` CLI reads the
    same one. Returns None when unset.
    """
    return os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or None


def read_anthropic_api_key() -> str | None:
    """API key for AsyncAnthropic (Stages [4]/[5] Haiku). Native ``ANTHROPIC_API_KEY``."""
    return os.environ.get("ANTHROPIC_API_KEY") or None


def resolve_github_token() -> str | None:
    """Resolve a GitHub token from the ambient environment.

    Returns the caller's ``GH_TOKEN``/``GITHUB_TOKEN``, or None if neither is set.
    The reusable workflow exports ``github.token``; locally it's the developer's
    ``gh auth`` token. No App minting — issues are authored by whoever owns the token.
    """
    return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
