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

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strict environment configuration. No defaults for secret-bearing fields.

    Every field holds a *resolved value* read straight from an ``AGENT_REFLECT_*``
    env var — the analyzer never reaches out to 1Password. Secret resolution
    (``op read`` / ``load-secrets-action``) happens outside, in the caller's CI
    workflow or the developer's credential-sync step.
    """

    model_config = SettingsConfigDict(
        env_prefix="AGENT_REFLECT_",
        extra="forbid",
        case_sensitive=False,
        populate_by_name=True,
    )

    # Full bucket URL, e.g. ``gs://my-bucket``. → AGENT_REFLECT_GCS_BUCKET
    gcs_bucket: str
    # Resolved GCS HMAC access key id (a value, not a 1P ref). → AGENT_REFLECT_HMAC_AKID
    hmac_akid: str
    # Resolved GCS HMAC secret (a value, not a 1P ref). → AGENT_REFLECT_HMAC_SECRET
    hmac_secret: str
    # Optional default org for ``--repo`` inference. → AGENT_REFLECT_TARGET_ORG_DEFAULT
    target_org_default: str | None = None


def load_settings() -> Settings:
    """Construct ``Settings`` from the environment. Raises on missing vars."""
    return Settings()  # type: ignore[call-arg]  # fields are sourced from env


# --- Non-secret constants -------------------------------------------------

GCS_RAW_PREFIX = "raw"
# Bucket layout version. v=2 adds the `org=<owner>` tenant partition under the
# raw prefix (`raw/v=2/org=<owner>/dev=<…>/proj=<…>/…`); the writer (ship.sh in
# the paired plugins task) and this reader move to it in lockstep. The legacy
# un-partitioned `raw/dev=*/proj=*` layout is cross-tenant-contaminated and is
# intentionally no longer read.
GCS_LAYOUT_VERSION = "v=2"
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
