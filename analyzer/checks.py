"""Pre-flight checks for the analyzer.

Each check returns a dict {id, category, ok, detail}. The CLI `--check` flag
runs all checks, prints a JSON array, and exits non-zero if any check failed
(unless --json is set, in which case it always exits 0 so the skill can parse
the result and present an actionable message).

Categories: env (binaries / env vars), secrets (1P), auth (network identity),
data (recent ships in bucket).
"""

from __future__ import annotations

import importlib
import os
import shutil
import sys
from typing import Any

from pydantic import ValidationError

from . import config, identity
from .config import Settings
from .subprocess_util import run_external

CheckResult = dict[str, Any]

_CONFIG_MISSING_DETAIL = (
    "analyzer configuration invalid — set the required AGENT_REFLECT_* environment "
    "variables (see README). A missing variable raises before any probe can run."
)


def _result(id_: str, category: str, ok: bool, detail: str) -> CheckResult:
    return {"id": id_, "category": category, "ok": ok, "detail": detail}


def _load_settings() -> Settings | None:
    """Load Settings, returning None (rather than raising) when env is incomplete."""
    try:
        return config.load_settings()
    except ValidationError:
        return None


def _op_read(ref: str) -> str | None:
    token = os.environ.get("OP_SVC_TOKEN")
    if not token:
        return None
    env = {**os.environ, "OP_SERVICE_ACCOUNT_TOKEN": token}
    try:
        out = run_external(["op", "read", ref], timeout=10, env=env, redact_argv_log=True).strip()
        return out or None
    except RuntimeError:
        return None


def check_hmac_1p() -> CheckResult:
    settings = _load_settings()
    if settings is None:
        return _result("hmac_1p", "secrets", False, _CONFIG_MISSING_DETAIL)
    val = _op_read(settings.hmac_akid_ref)
    if val is None:
        return _result(
            "hmac_1p",
            "secrets",
            False,
            "1P reference not readable. Set OP_SVC_TOKEN in env to a "
            "1Password service-account token, then restart the Claude session so "
            "the SessionStart hook picks it up. If `op read` itself fails, the "
            "service account lacks access to the referenced vault.",
        )
    if len(val) < 30:
        return _result(
            "hmac_1p",
            "secrets",
            False,
            f"access_key_id length={len(val)} chars — expected ≥30 (likely 60).",
        )
    return _result("hmac_1p", "secrets", True, f"access_key_id length={len(val)} chars OK.")


def check_gh_cli() -> CheckResult:
    if not shutil.which("gh"):
        return _result("gh_cli", "auth", False, "gh CLI not on PATH (`brew install gh`).")
    try:
        run_external(["gh", "auth", "status"], timeout=10, env={**os.environ})
        return _result("gh_cli", "auth", True, "gh auth status OK.")
    except RuntimeError as e:
        return _result(
            "gh_cli",
            "auth",
            False,
            f"gh auth status failed — run `gh auth login`. ({str(e)[:80]})",
        )


def check_recent_ships() -> CheckResult:
    """Liveness probe for shipped sessions via the SAME DuckDB/HMAC path as real
    ingestion (PF-26).

    The old probe used `gsutil ls` (gcloud OAuth) while ingestion uses
    DuckDB + HMAC — so an expired gcloud OAuth produced a false negative even
    when the live path worked. Scope to the caller's own `dev=<dev>` partition
    under the `v=2` layout; `org=*` here only enumerates the caller's own
    filenames (a liveness count, not a cross-tenant content read).
    """
    try:
        import duckdb
    except ImportError:
        return _result("recent_ships", "data", False, "duckdb module not importable.")
    settings = _load_settings()
    if settings is None:
        return _result("recent_ships", "data", False, _CONFIG_MISSING_DETAIL)
    key_id = _op_read(settings.hmac_akid_ref)
    secret = _op_read(settings.hmac_secret_ref)
    if not key_id or not secret:
        return _result(
            "recent_ships",
            "data",
            False,
            "HMAC pair unavailable from 1P (covered by hmac_1p probe).",
        )
    try:
        dev = identity.dev_id()
    except RuntimeError:
        return _result("recent_ships", "data", False, "git user.email empty — set it.")
    pattern = (
        f"{settings.gcs_bucket}/{config.GCS_RAW_PREFIX}/{config.GCS_LAYOUT_VERSION}"
        f"/org=*/dev={dev}/proj=*/*.jsonl"
    )
    try:
        con = duckdb.connect(":memory:")
        con.execute("INSTALL httpfs; LOAD httpfs;")
        con.execute("CREATE SECRET (TYPE gcs, KEY_ID ?, SECRET ?);", [key_id, secret])
        row = con.execute("SELECT count(*) FROM glob(?)", [pattern]).fetchone()
        con.close()
        n = int(row[0]) if row else 0
        if not n:
            return _result(
                "recent_ships",
                "data",
                False,
                f"No shipped sessions for dev={dev} in the {config.GCS_LAYOUT_VERSION} layout.",
            )
        return _result(
            "recent_ships", "data", True, f"{n} shipped session file(s) via DuckDB/HMAC."
        )
    except Exception as e:  # pragma: no cover - defensive
        return _result(
            "recent_ships",
            "data",
            False,
            f"DuckDB glob failed: {type(e).__name__}: {str(e)[:80]}",
        )


def check_anthropic_key() -> CheckResult:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        settings = _load_settings()
        if settings is None:
            return _result("anthropic_key", "secrets", False, _CONFIG_MISSING_DETAIL)
        # Try fallback from 1P. Skill auto-bootstraps env using the same ref.
        key = _op_read(settings.anthropic_key_ref)
        if key:
            os.environ["ANTHROPIC_API_KEY"] = key
            return _result(
                "anthropic_key",
                "secrets",
                True,
                "ANTHROPIC_API_KEY loaded from 1P via AGENT_REFLECT_ANTHROPIC_KEY_REF.",
            )
        return _result(
            "anthropic_key",
            "secrets",
            False,
            "ANTHROPIC_API_KEY env not set and 1P fallback unavailable. Usually "
            "caused by a missing OP_SVC_TOKEN (see hmac_1p detail) — fix "
            "that first and this probe auto-recovers via the 1P fallback.",
        )
    if len(key) < 20:
        return _result("anthropic_key", "secrets", False, "ANTHROPIC_API_KEY suspiciously short.")
    return _result("anthropic_key", "secrets", True, "ANTHROPIC_API_KEY present.")


def check_claude_cli() -> CheckResult:
    if not shutil.which("claude"):
        return _result(
            "claude_cli",
            "env",
            False,
            "claude CLI missing — install Claude Code.",
        )
    try:
        run_external(["claude", "-p", "--help"], timeout=5, env={**os.environ})
        return _result("claude_cli", "env", True, "claude -p --help OK.")
    except RuntimeError as e:
        return _result("claude_cli", "env", False, f"claude -p --help failed: {str(e)[:80]}")


_PY_DEPS = [
    "duckdb",
    "semhash",
    "presidio_analyzer",
    "sentence_transformers",
    "sklearn",
    "anthropic",
    "jinja2",
    "click",
    "pydantic",
    "tenacity",
]


def bootstrap_anthropic_key() -> bool:
    """Ensure os.environ['ANTHROPIC_API_KEY'] is set, loading from 1P if needed.

    Called at the start of pipeline runs (not just --check), so AsyncAnthropic()
    finds a key when constructed later. Returns True if key is present (env or
    successfully bootstrapped from 1P), False otherwise.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    settings = _load_settings()
    if settings is None:
        return False
    val = _op_read(settings.anthropic_key_ref)
    if val:
        os.environ["ANTHROPIC_API_KEY"] = val
        return True
    return False


def check_python_deps() -> CheckResult:
    # `mod` comes only from the static _PY_DEPS list above — not user input.
    missing: list[str] = []
    for mod in _PY_DEPS:
        try:
            # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
            importlib.import_module(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        return _result(
            "python_deps",
            "env",
            False,
            f"missing modules: {', '.join(missing)} (run `uv sync --extra dev`).",
        )
    return _result("python_deps", "env", True, f"all {len(_PY_DEPS)} modules importable.")


def check_hmac_duckdb_smoke() -> CheckResult:
    """End-to-end: open DuckDB connection through HMAC and list 1 object.

    Skips silently if duckdb or 1P aren't ready; those failures are surfaced by
    other probes.
    """
    try:
        import duckdb  # noqa: F401
    except ImportError:
        return _result("hmac_duckdb_smoke", "data", False, "duckdb module not importable.")
    settings = _load_settings()
    if settings is None:
        return _result("hmac_duckdb_smoke", "data", False, _CONFIG_MISSING_DETAIL)
    key_id = _op_read(settings.hmac_akid_ref)
    secret = _op_read(settings.hmac_secret_ref)
    if not key_id or not secret:
        return _result(
            "hmac_duckdb_smoke",
            "data",
            False,
            "HMAC pair unavailable from 1P (covered by hmac_1p probe).",
        )
    try:
        import duckdb

        con = duckdb.connect(":memory:")
        con.execute("INSTALL httpfs; LOAD httpfs;")
        con.execute(
            "CREATE SECRET (TYPE gcs, KEY_ID ?, SECRET ?);",
            [key_id, secret],
        )
        con.execute("SELECT 1").fetchall()
        con.close()
        return _result("hmac_duckdb_smoke", "data", True, "DuckDB GCS secret loaded OK.")
    except Exception as e:  # pragma: no cover - defensive
        return _result(
            "hmac_duckdb_smoke",
            "data",
            False,
            f"DuckDB GCS smoke failed: {type(e).__name__}: {str(e)[:80]}",
        )


PROBES = [
    check_hmac_1p,
    check_hmac_duckdb_smoke,
    check_gh_cli,
    check_recent_ships,
    check_anthropic_key,
    check_claude_cli,
    check_python_deps,
]


def run_all() -> list[CheckResult]:
    return [p() for p in PROBES]


def all_ok(results: list[CheckResult]) -> bool:
    return all(r["ok"] for r in results)


def print_human(results: list[CheckResult], stream=None) -> None:
    if stream is None:
        stream = sys.stdout
    for r in results:
        marker = "OK " if r["ok"] else "FAIL"
        stream.write(f"[{marker}] {r['id']:24s} ({r['category']}) {r['detail']}\n")
