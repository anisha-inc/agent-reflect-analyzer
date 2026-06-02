"""Tests for analyzer.duckdb_query — mock-based aggregation tests + duration parsing."""

from __future__ import annotations

import datetime as dt

import pytest

from analyzer import duckdb_query


def test_parse_duration_days():
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = duckdb_query.parse_duration("7d")
    delta = now - cutoff
    assert dt.timedelta(days=6, hours=23) < delta < dt.timedelta(days=7, hours=1)


def test_parse_duration_hours():
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = duckdb_query.parse_duration("12h")
    delta = now - cutoff
    assert dt.timedelta(hours=11, minutes=59) < delta < dt.timedelta(hours=12, minutes=1)


def test_parse_duration_weeks():
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = duckdb_query.parse_duration("2w")
    delta = now - cutoff
    assert dt.timedelta(days=13) < delta < dt.timedelta(days=15)


def test_parse_duration_invalid():
    with pytest.raises(ValueError):
        duckdb_query.parse_duration("nonsense")


def test_aggregate_session_counts_tool_uses_and_errors():
    events = [
        {
            "type": "user",
            "timestamp": "2026-05-25T12:17:05.459Z",
            "message": {"role": "user", "content": "do the thing"},
        },
        {
            "type": "assistant",
            "timestamp": "2026-05-25T12:17:06.000Z",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "ok"},
                    {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
                ],
                "usage": {"input_tokens": 100, "output_tokens": 20},
            },
        },
        {
            "type": "user",
            "timestamp": "2026-05-25T12:17:07.000Z",
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "is_error": True, "content": "ls: command failed"},
                ],
            },
        },
    ]
    agg = duckdb_query._aggregate_session(events)
    assert agg["tool_calls"] == 1
    assert agg["errors"] == 1
    assert agg["tool_diversity"] == 1
    assert "Bash" in agg["tools_chained"]
    assert agg["max_input_tokens"] == 100
    assert agg["total_output_tokens"] == 20
    assert agg["error_classes"] == ["ls: command failed"]


def test_session_first_user_prompt_picks_first_non_meta():
    events = [
        {"type": "user", "isMeta": True, "message": {"role": "user", "content": "<caveat>"}},
        {"type": "user", "message": {"role": "user", "content": "actual prompt"}},
    ]
    assert duckdb_query._session_first_user_prompt(events) == "actual prompt"


def test_load_sessions_filters_reflect_sessions():
    """End-to-end mock test of load_sessions — supply a fake connection that
    returns 2 sessions, one of which is a /reflect-agent-sessions invocation."""

    class FakeCursor:
        description = [("type",), ("sessionId",), ("timestamp",), ("message",), ("isMeta",)]

    class FakeCon:
        description = FakeCursor.description

        def execute(self, sql, params=None):
            return self

        def fetchall(self):
            return [
                (
                    "user",
                    "sess-A",
                    "2026-05-25T10:00:00Z",
                    {"role": "user", "content": "/reflect-agent-sessions --since 7d"},
                    False,
                ),
                (
                    "user",
                    "sess-B",
                    "2026-05-25T11:00:00Z",
                    {"role": "user", "content": "fix the bug in foo.py"},
                    False,
                ),
                (
                    "assistant",
                    "sess-B",
                    "2026-05-25T11:00:05Z",
                    {
                        "role": "assistant",
                        "content": [{"type": "tool_use", "name": "Read", "input": {}}],
                        "usage": {"input_tokens": 50, "output_tokens": 10},
                    },
                    False,
                ),
            ]

    sessions = duckdb_query.load_sessions(FakeCon(), since="7d", limit=10)
    # sess-A is dropped by the reflect filter.
    sids = [s["sessionId"] for s in sessions]
    assert sids == ["sess-B"]
    assert sessions[0]["tool_calls"] == 1
