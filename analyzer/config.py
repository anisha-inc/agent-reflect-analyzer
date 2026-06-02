"""Shared constants and runtime configuration for the analyzer."""

from __future__ import annotations

import os
import pathlib

GCS_BUCKET = "gs://anisha-claude-logs"
GCS_RAW_PREFIX = "raw"
GCS_S3_ENDPOINT = "storage.googleapis.com"

HMAC_OP_ITEM = "op://Atlas Agent/claude-logs-hmac"
HMAC_ACCESS_KEY_REF = f"{HMAC_OP_ITEM}/access_key_id"
HMAC_SECRET_KEY_REF = f"{HMAC_OP_ITEM}/secret_access_key"

# NB: 1P item is misspelled "Antropic" (created 2026-05-25). Renaming would be
# scoped, opaque, and out of this PR — we ref the actual title.
#
# Two distinct tokens for two distinct billing paths:
#   - ANTHROPIC_KEY_REF: API key for AsyncAnthropic (Stages [4]/[5] Haiku).
#                        Pay-per-call billing (~$0.01 per Haiku request).
#   - OAUTH_TOKEN_REF:   Long-life OAuth token for `claude -p` subprocess
#                        (Stage [3] Opus). Subscription billing (Pro/Max/
#                        Enterprise), $0 marginal. Set as CLAUDE_CODE_OAUTH_TOKEN
#                        in the subprocess env; the CLI reads it natively.
ANTHROPIC_KEY_REF = "op://Atlas Agent/Antropic/atlas-agent-test-key/ANTHROPIC_API_KEY"
# Vladimir renamed `CLAUDE_CODE_OAUTH_TOKEN___` → `CLAUDE_CODE_OAUTH_TOKEN`
# on 2026-05-27; auth.read_oauth_token() tries both during transition.
OAUTH_TOKEN_REFS = (
    "op://Atlas Agent/Antropic/atlas-agent-test-key/CLAUDE_CODE_OAUTH_TOKEN",
    "op://Atlas Agent/Antropic/atlas-agent-test-key/CLAUDE_CODE_OAUTH_TOKEN___",
)

ISSUE_LABEL = "improvement-by-agent"
DEFAULT_TARGET_ORG = "anisha-inc"

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
