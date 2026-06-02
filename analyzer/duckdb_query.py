"""DuckDB ingestion against shipped session JSONL in GCS.

DuckDB connects via httpfs + GCS HMAC secret (atlas#413 provisioned). Sessions
are loaded as raw JSON, then aggregated per session in Python (the nested
content[] arrays are non-trivial to flatten in SQL alone — see jsonl-schema.md).

`load_sessions()` returns the ranked + capped list (uses metrics.interestingness
for ordering, applies `/reflect-agent-sessions` self-pollution filter from
PRD §C3). `load_events_for_sessions()` returns all events grouped by sessionId
for the LLM stages.

Functions are designed to gracefully degrade: when DuckDB / 1P / httpfs are
absent (CI lane, no creds in env), import-time guards keep the module loadable
so unit tests can mock the connection.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from . import config

_DURATION_RE = re.compile(r"^(?P<num>\d+)\s*(?P<unit>[dhmw]?)$")


def parse_duration(since: str) -> datetime:
    """Convert `7d` / `14d` / `30d` / `12h` to an aware UTC cutoff."""
    m = _DURATION_RE.match(since.strip().lower())
    if not m:
        raise ValueError(f"Invalid --since: {since!r}. Use Nd / Nh / Nm / Nw.")
    n = int(m.group("num"))
    unit = m.group("unit") or "d"
    delta = {
        "m": timedelta(minutes=n),
        "h": timedelta(hours=n),
        "d": timedelta(days=n),
        "w": timedelta(weeks=n),
    }[unit]
    return datetime.now(timezone.utc) - delta


def _op_read(ref: str) -> str:
    """Read a 1P secret reference. Raises if ANISHA_OP_SVC_TOKEN missing."""
    token = os.environ.get("ANISHA_OP_SVC_TOKEN")
    if not token:
        raise RuntimeError("ANISHA_OP_SVC_TOKEN not set — cannot read 1P secret.")
    env = {**os.environ, "OP_SERVICE_ACCOUNT_TOKEN": token}
    out = subprocess.check_output(
        ["op", "read", ref], env=env, text=True, stderr=subprocess.PIPE
    ).strip()
    if not out:
        raise RuntimeError(f"op read {ref} returned empty string.")
    return out


def connect():
    """Open a DuckDB in-memory connection with httpfs + GCS HMAC secret loaded."""
    import duckdb  # local: keep top-level import optional for unit tests

    key_id = _op_read(config.HMAC_ACCESS_KEY_REF)
    secret = _op_read(config.HMAC_SECRET_KEY_REF)
    con = duckdb.connect(":memory:")
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(
        "CREATE OR REPLACE SECRET (TYPE gcs, KEY_ID ?, SECRET ?);",
        [key_id, secret],
    )
    return con


def _glob() -> str:
    return f"{config.GCS_BUCKET}/{config.GCS_RAW_PREFIX}/dev=*/proj=*/*.jsonl"


def fetch_raw(con, since: str, hard_limit: int | None = None) -> list[dict[str, Any]]:
    """Pull raw JSONL rows from GCS within `since` window.

    Returns a list of dicts with original event shape preserved.
    """
    cutoff = parse_duration(since)
    # No user input in the SQL — _glob() returns a constant from analyzer.config;
    # the only dynamic value (cutoff) is passed as a parameter binding below.
    sql = f"""
        SELECT * FROM read_json_auto(
            '{_glob()}',
            format='newline_delimited',
            union_by_name=true,
            ignore_errors=true
        )
        WHERE timestamp >= ? :: TIMESTAMP
    """
    if hard_limit:
        # int() coercion guarantees this is a literal integer.
        sql += f" LIMIT {int(hard_limit)}"
    # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
    rows = con.execute(sql, [cutoff.isoformat()]).fetchall()
    columns = [d[0] for d in con.description]
    return [_row_to_dict(r, columns) for r in rows]


def _row_to_dict(row: tuple, columns: list[str]) -> dict[str, Any]:
    """Convert DuckDB row (tuple) → dict, normalizing types.

    DuckDB:
      - returns nested fields as Python objects already (dict / list);
      - returns UUID columns as `uuid.UUID` instances — coerced to str so the
        rest of the pipeline can use them as dict keys.
      - returns string-encoded JSON for some columns when `union_by_name=true`
        couldn't decide on a type — parse opportunistically.
    """
    import uuid

    out: dict[str, Any] = {}
    for col, val in zip(columns, row):
        if val is None:
            continue
        if isinstance(val, uuid.UUID):
            out[col] = str(val)
            continue
        if isinstance(val, str) and col in ("message", "content", "toolUseResult"):
            try:
                out[col] = json.loads(val)
                continue
            except json.JSONDecodeError:
                pass
        out[col] = val
    return out


def _content_blocks(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize `message.content` to a list of block dicts.

    DuckDB's `union_by_name=true` collapses heterogeneous schemas (user.content
    string vs assistant.content array) to VARCHAR; opportunistically parse JSON
    strings back to lists. Plain text user prompts stay as strings (and are
    returned as zero-block lists by this function — handled separately by
    `_session_first_user_prompt`).
    """
    msg = event.get("message")
    if not isinstance(msg, dict):
        return []
    c = msg.get("content")
    if isinstance(c, str):
        try:
            c = json.loads(c)
        except json.JSONDecodeError:
            return []
    if isinstance(c, list):
        return [b for b in c if isinstance(b, dict)]
    return []


def _session_first_user_prompt(events: list[dict[str, Any]]) -> str | None:
    for e in events:
        if e.get("type") != "user":
            continue
        if e.get("isMeta"):
            continue
        msg = e.get("message") or {}
        c = msg.get("content")
        if isinstance(c, str):
            try:
                parsed = json.loads(c)
            except json.JSONDecodeError:
                return c
            if isinstance(parsed, list):
                c = parsed
            else:
                return c if isinstance(c, str) else None
        if isinstance(c, list):
            for b in c:
                if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str):
                    return b["text"]
    return None


def _aggregate_session(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute baseline metrics for a single session."""
    tool_calls = 0
    errors = 0
    tool_names: dict[str, int] = defaultdict(int)
    max_input_tokens = 0
    total_output_tokens = 0
    timestamps: list[str] = []
    last_assistant_text: str = ""
    error_classes: list[str] = []

    for e in events:
        t = e.get("type")
        ts = e.get("timestamp")
        if isinstance(ts, str):
            timestamps.append(ts)

        if t == "assistant":
            blocks = _content_blocks(e)
            for b in blocks:
                bt = b.get("type")
                if bt == "tool_use":
                    tool_calls += 1
                    name = b.get("name")
                    if isinstance(name, str):
                        tool_names[name] += 1
                elif bt == "text" and isinstance(b.get("text"), str):
                    last_assistant_text = b["text"]
            msg = e.get("message") or {}
            usage = msg.get("usage") if isinstance(msg, dict) else None
            if isinstance(usage, dict):
                inp = (
                    int(usage.get("input_tokens") or 0)
                    + int(usage.get("cache_creation_input_tokens") or 0)
                    + int(usage.get("cache_read_input_tokens") or 0)
                )
                if inp > max_input_tokens:
                    max_input_tokens = inp
                total_output_tokens += int(usage.get("output_tokens") or 0)

        elif t == "user":
            blocks = _content_blocks(e)
            for b in blocks:
                if b.get("type") == "tool_result" and b.get("is_error") is True:
                    errors += 1
                    payload = b.get("content")
                    if isinstance(payload, str):
                        # First line / first 80 chars as error class.
                        error_classes.append(payload.splitlines()[0][:80])
                    elif isinstance(payload, list):
                        for sub in payload:
                            if isinstance(sub, dict) and isinstance(sub.get("text"), str):
                                error_classes.append(sub["text"].splitlines()[0][:80])
                                break

    started_at = min(timestamps) if timestamps else None
    ended_at = max(timestamps) if timestamps else None
    return {
        "tool_calls": tool_calls,
        "errors": errors,
        "tool_diversity": len(tool_names),
        "tools_chained": sorted(tool_names, key=tool_names.get, reverse=True)[:3],
        "max_input_tokens": max_input_tokens,
        "total_output_tokens": total_output_tokens,
        "started_at": started_at,
        "ended_at": ended_at,
        "last_assistant_text": last_assistant_text,
        "error_classes": error_classes[:5],
    }


def load_sessions(con, since: str, limit: int) -> list[dict[str, Any]]:
    """Return ranked + capped sessions with baseline metrics.

    Pulls all events within `since`, groups by sessionId, computes metrics,
    filters self-pollution, scores by interestingness, returns top `limit`.
    """
    from . import metrics  # local: avoid circular when metrics imports config

    raw = fetch_raw(con, since=since)
    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ev in raw:
        sid = ev.get("sessionId")
        if isinstance(sid, str):
            by_session[sid].append(ev)

    sessions: list[dict[str, Any]] = []
    for sid, events in by_session.items():
        first = _session_first_user_prompt(events)
        if metrics.is_reflect_session(first):
            continue
        agg = _aggregate_session(events)
        agg.update({
            "sessionId": sid,
            "first_user_prompt": first or "",
            "score": 0.0,
        })
        agg["score"] = metrics.interestingness_score(agg)
        sessions.append(agg)

    sessions.sort(key=lambda s: s["score"], reverse=True)
    return sessions[:limit]


def load_events_for_sessions(
    con, session_ids: list[str], since: str = "30d"
) -> dict[str, list[dict[str, Any]]]:
    """Return events grouped by sessionId, restricted to the supplied ids."""
    if not session_ids:
        return {}
    raw = fetch_raw(con, since=since)
    wanted = set(session_ids)
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ev in raw:
        sid = ev.get("sessionId")
        if sid in wanted:
            out[sid].append(ev)
    # Sort each session's events by timestamp.
    for sid in out:
        out[sid].sort(key=lambda e: e.get("timestamp") or "")
    return dict(out)
