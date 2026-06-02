"""Runtime configuration for the analyzer.

Secret- and environment-dependent settings live in the strict ``Settings``
pydantic-settings model: every field is required, has no default, and is read
from an ``AGENT_REFLECT_*`` environment variable. Loading with a missing
variable raises ``pydantic.ValidationError`` — fail fast, never fall back to a
hard-coded value.

Non-secret tunables (model names, default window, label) stay as module-level
constants below.
"""

from __future__ import annotations

import os
import pathlib
from typing import Annotated

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Strict environment configuration. No defaults for secret-bearing fields."""

    model_config = SettingsConfigDict(
        env_prefix="AGENT_REFLECT_",
        extra="forbid",
        case_sensitive=False,
        populate_by_name=True,
    )

    # Full bucket URL, e.g. ``gs://my-bucket``. → AGENT_REFLECT_GCS_BUCKET
    gcs_bucket: str
    # 1Password reference for the GCS HMAC access key id. → AGENT_REFLECT_HMAC_AKID_REF
    hmac_akid_ref: str
    # 1Password reference for the GCS HMAC secret. → AGENT_REFLECT_HMAC_SECRET_REF
    hmac_secret_ref: str
    # 1Password reference for the Anthropic API key. → AGENT_REFLECT_ANTHROPIC_KEY_REF
    anthropic_key_ref: str
    # Comma-separated 1Password references for the ``claude -p`` OAuth token.
    # → AGENT_REFLECT_OAUTH_TOKEN_REF (singular env var, list-valued field).
    oauth_token_refs: Annotated[list[str], NoDecode] = Field(
        validation_alias=AliasChoices("AGENT_REFLECT_OAUTH_TOKEN_REF", "oauth_token_refs"),
    )
    # Optional default org for ``--repo`` inference. → AGENT_REFLECT_TARGET_ORG_DEFAULT
    target_org_default: str | None = None

    @field_validator("oauth_token_refs", mode="before")
    @classmethod
    def _split_oauth_refs(cls, v: object) -> object:
        """Split the comma-separated env value; an empty string is invalid.

        Defense-in-depth interface contract: an explicitly empty
        ``AGENT_REFLECT_OAUTH_TOKEN_REF`` must raise, not silently yield ``[]``.
        """
        if isinstance(v, str):
            parts = [p.strip() for p in v.split(",") if p.strip()]
            if not parts:
                raise ValueError(
                    "AGENT_REFLECT_OAUTH_TOKEN_REF must list at least one 1Password reference"
                )
            return parts
        return v


def load_settings() -> Settings:
    """Construct ``Settings`` from the environment. Raises on missing vars."""
    return Settings()  # type: ignore[call-arg]  # fields are sourced from env


# --- Non-secret constants -------------------------------------------------

GCS_RAW_PREFIX = "raw"
GCS_S3_ENDPOINT = "storage.googleapis.com"

ISSUE_LABEL = "improvement-by-agent"

DEFAULT_TOP_K = 10
DEFAULT_CONCURRENCY = 10
DEFAULT_MIN_CLUSTER_FREQ = 3
DEFAULT_OPUS_MODEL = "claude-opus-4-7"
DEFAULT_HAIKU_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_SINCE = "7d"
DEFAULT_LIMIT = 50

PLUGIN_DATA_ROOT = pathlib.Path(
    os.environ.get(
        "CLAUDE_PLUGIN_DATA",
        os.environ.get("XDG_STATE_HOME", str(pathlib.Path.home() / ".local" / "state"))
        + "/agent-reflect",
    )
)
AUDIT_DIR = PLUGIN_DATA_ROOT / "audit"
