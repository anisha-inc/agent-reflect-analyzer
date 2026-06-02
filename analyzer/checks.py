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
import subprocess
import sys
from typing import Any

from . import config, identity

CheckResult = dict[str, Any]


def _result(id_: str, category: str, ok: bool, detail: str) -> CheckResult:
    return {"id": id_, "category": category, "ok": ok, "detail": detail}


def _op_read(ref: str) -> str | None:
    token = os.environ.get("ANISHA_OP_SVC_TOKEN")
    if not token:
        return None
    env = {**os.environ, "OP_SERVICE_ACCOUNT_TOKEN": token}
    try:
        out = subprocess.check_output(
            ["op", "read", ref], env=env, text=True, stderr=subprocess.DEVNULL, timeout=10
        ).strip()
        return out or None
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def check_hmac_1p() -> CheckResult:
    val = _op_read(config.HMAC_ACCESS_KEY_REF)
    if val is None:
        return _result(
            "hmac_1p", "secrets", False,
            "1P item not readable. Fix: in a fresh terminal run "
            "`export ANISHA_OP_SVC_TOKEN=\"$(op read 'op://Speedy Shared/1Password/SERVICE_ACCOUNT_TOKEN__ATLAS_AGENT_ACCESS')\"` "
            "(unlocks via 1P desktop / touchID), then restart Claude session so SessionStart hook picks it up. "
            "If `op read` itself fails — atlas#413 provisioning didn't reach your vault.",
        )
    if len(val) < 30:
        return _result(
            "hmac_1p", "secrets", False,
            f"access_key_id length={len(val)} chars — expected ≥30 (likely 60).",
        )
    return _result("hmac_1p", "secrets", True, f"access_key_id length={len(val)} chars OK.")


def check_gh_cli() -> CheckResult:
    if not shutil.which("gh"):
        return _result("gh_cli", "auth", False, "gh CLI not on PATH (`brew install gh`).")
    try:
        subprocess.check_output(
            ["gh", "auth", "status"], stderr=subprocess.STDOUT, text=True, timeout=10
        )
        return _result("gh_cli", "auth", True, "gh auth status OK.")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        return _result(
            "gh_cli", "auth", False,
            f"gh auth status failed — run `gh auth login`. ({str(e)[:80]})",
        )


def check_app_token_script() -> CheckResult:
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        path = os.path.join(plugin_root, "scripts", "github-app-token")
    else:
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "scripts", "github-app-token"
        )
    if not os.path.isfile(path):
        return _result(
            "app_token", "auth", False,
            f"github-app-token script missing at {path} (run /sync-settings).",
        )
    if not os.access(path, os.X_OK):
        return _result("app_token", "auth", False, f"{path} not executable (chmod +x).")
    try:
        subprocess.check_output([path, "--help"], stderr=subprocess.STDOUT, timeout=5)
        return _result("app_token", "auth", True, "github-app-token --help OK.")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        return _result("app_token", "auth", False, f"--help failed: {str(e)[:80]}")


def check_recent_ships() -> CheckResult:
    if not shutil.which("gsutil"):
        return _result(
            "recent_ships", "data", False,
            "gsutil missing (`brew install google-cloud-sdk`).",
        )
    try:
        dev = identity.dev_id()
    except (RuntimeError, subprocess.CalledProcessError):
        return _result("recent_ships", "data", False, "git user.email empty — set it.")
    url = f"{config.GCS_BUCKET}/{config.GCS_RAW_PREFIX}/dev={dev}/"
    try:
        out = subprocess.check_output(
            ["gsutil", "ls", url], stderr=subprocess.STDOUT, text=True, timeout=20
        )
        lines = [l for l in out.strip().splitlines() if l.strip()]
        if not lines:
            return _result(
                "recent_ships", "data", False,
                f"No shipped sessions found in {url}.",
            )
        return _result("recent_ships", "data", True, f"{len(lines)} project(s) shipped.")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        return _result(
            "recent_ships", "data", False,
            f"gsutil ls failed: {str(e)[:80]}",
        )


def check_anthropic_key() -> CheckResult:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        # Try fallback from 1P. Skill auto-bootstraps env using same ref.
        key = _op_read(config.ANTHROPIC_KEY_REF)
        if key:
            os.environ["ANTHROPIC_API_KEY"] = key
            return _result(
                "anthropic_key", "secrets", True,
                "ANTHROPIC_API_KEY loaded from 1P (op://Atlas Agent/Antropic/.../ANTHROPIC_API_KEY).",
            )
        return _result(
            "anthropic_key", "secrets", False,
            "ANTHROPIC_API_KEY env not set and 1P fallback unavailable. "
            "Usually caused by missing ANISHA_OP_SVC_TOKEN (see hmac_1p detail) — fix that first, "
            "this probe will auto-recover via 1P fallback. As a manual fallback: "
            "`export ANTHROPIC_API_KEY=\"$(op read 'op://Atlas Agent/Antropic/atlas-agent-test-key/ANTHROPIC_API_KEY')\"`.",
        )
    if len(key) < 20:
        return _result("anthropic_key", "secrets", False, "ANTHROPIC_API_KEY suspiciously short.")
    return _result("anthropic_key", "secrets", True, "ANTHROPIC_API_KEY present.")


def check_claude_cli() -> CheckResult:
    if not shutil.which("claude"):
        return _result(
            "claude_cli", "env", False,
            "claude CLI missing — install Claude Code.",
        )
    try:
        subprocess.check_output(
            ["claude", "-p", "--help"], stderr=subprocess.STDOUT, text=True, timeout=5
        )
        return _result("claude_cli", "env", True, "claude -p --help OK.")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
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
    val = _op_read(config.ANTHROPIC_KEY_REF)
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
            "python_deps", "env", False,
            f"missing modules: {', '.join(missing)} (run `uv sync` in lib/analyzer/).",
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
    key_id = _op_read(config.HMAC_ACCESS_KEY_REF)
    secret = _op_read(config.HMAC_SECRET_KEY_REF)
    if not key_id or not secret:
        return _result(
            "hmac_duckdb_smoke", "data", False,
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
            "hmac_duckdb_smoke", "data", False,
            f"DuckDB GCS smoke failed: {type(e).__name__}: {str(e)[:80]}",
        )


PROBES = [
    check_hmac_1p,
    check_hmac_duckdb_smoke,
    check_gh_cli,
    check_app_token_script,
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
