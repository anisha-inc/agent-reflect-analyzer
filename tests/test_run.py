"""Tests for analyzer.run — pipeline orchestration with mocked stages."""

from __future__ import annotations

from unittest.mock import patch

from analyzer import audit, run
from analyzer.llm.schemas import Candidate


def test_run_pipeline_empty_bucket_returns_baseline_summary():
    """When DuckDB returns 0 sessions, summary still has the expected shape."""
    record = audit.RunRecord()
    with (
        patch("analyzer.duckdb_query.connect") as conn,
        patch("analyzer.duckdb_query.load_sessions", return_value=[]),
    ):
        conn.return_value.close = lambda: None
        summary = run.run_pipeline(
            record=record,
            since="7d",
            limit=10,
            repo=None,
            read_owner="acme",
            emit_issues=False,
            top_k=10,
            strategy="hybrid",
            model_top_k="opus",
            model_rest="haiku",
            concurrency=3,
            cluster=False,
            include_closed_since=None,
            api_key_fallback=False,
            verbose=False,
        )
    assert summary["sessions_analyzed"] == 0
    assert summary["candidates_total"] == 0
    assert summary["issue_urls"] == []
    assert "total_wall_s" in summary


def test_run_pipeline_dry_run_does_not_call_emit():
    record = audit.RunRecord()
    fake_candidate = Candidate(
        source="opus_top_k",
        pattern_id="x",
        title="t",
        frequency=2,
        symptom="s",
        proposed_fix="f",
    )
    with (
        patch("analyzer.duckdb_query.connect") as conn,
        patch("analyzer.duckdb_query.load_sessions", return_value=[{"sessionId": "s1"}]),
        patch("analyzer.duckdb_query.load_events_for_sessions", return_value={"s1": []}),
        patch("analyzer.llm.pipeline.run", return_value=[fake_candidate]),
        patch("analyzer.issues.emit_issue") as emit,
    ):
        conn.return_value.close = lambda: None
        summary = run.run_pipeline(
            record=record,
            since="7d",
            limit=10,
            repo=None,
            read_owner="acme",
            emit_issues=False,
            top_k=10,
            strategy="hybrid",
            model_top_k="opus",
            model_rest="haiku",
            concurrency=3,
            cluster=False,
            include_closed_since=None,
            api_key_fallback=False,
            verbose=False,
        )
    assert summary["candidates_total"] == 1
    assert summary["issues_emitted"] == 0
    emit.assert_not_called()
    # body_preview was rendered for UX
    assert summary["candidates"][0].get("body_preview") is not None


def test_run_pipeline_emit_issues_calls_gh():
    record = audit.RunRecord()
    fake_candidate = Candidate(
        source="opus_top_k",
        pattern_id="x",
        title="t",
        frequency=2,
        symptom="s",
        proposed_fix="f",
    )
    with (
        patch("analyzer.duckdb_query.connect") as conn,
        patch("analyzer.duckdb_query.load_sessions", return_value=[{"sessionId": "s1"}]),
        patch("analyzer.duckdb_query.load_events_for_sessions", return_value={"s1": []}),
        patch("analyzer.llm.pipeline.run", return_value=[fake_candidate]),
        patch("analyzer.dedup.fetch_open_issues", return_value=[]),
        patch("analyzer.dedup.dedup_candidates", return_value=[fake_candidate]),
        patch("analyzer.redact.redact_candidate", return_value=fake_candidate),
        patch("analyzer.auth.resolve_github_token", return_value="ghs_dummy"),
        patch("analyzer.issues.emit_issue", return_value="https://github.com/a/b/issues/1") as emit,
    ):
        conn.return_value.close = lambda: None
        summary = run.run_pipeline(
            record=record,
            since="7d",
            limit=10,
            repo="a/b",
            read_owner="a",
            emit_issues=True,
            top_k=10,
            strategy="hybrid",
            model_top_k="opus",
            model_rest="haiku",
            concurrency=3,
            cluster=False,
            include_closed_since=None,
            api_key_fallback=False,
            verbose=False,
        )
    assert summary["issues_emitted"] == 1
    assert summary["issue_urls"] == ["https://github.com/a/b/issues/1"]
    emit.assert_called_once()
