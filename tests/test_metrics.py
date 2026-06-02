"""Tests for analyzer.metrics — scoring + heuristics + reflect filter."""

from __future__ import annotations

from analyzer import metrics


def test_interestingness_score_zero_for_empty_session():
    assert metrics.interestingness_score({}) == 0.0


def test_interestingness_score_weights_errors_and_retries():
    s_no = metrics.interestingness_score({"errors": 0, "retry_loops": 0})
    s_err = metrics.interestingness_score({"errors": 5, "retry_loops": 0})
    s_loop = metrics.interestingness_score({"errors": 0, "retry_loops": 5})
    assert s_loop > s_err > s_no
    # 5 retry_loops × 5.0 = 25; 5 errors × 3.0 = 15.
    assert abs(s_err - 15.0) < 1e-6
    assert abs(s_loop - 25.0) < 1e-6


def test_is_reflect_session_matches_slash_command():
    assert metrics.is_reflect_session("/reflect-agent-sessions --since 7d")
    assert metrics.is_reflect_session("Run /reflect-agent-sessions please")
    assert not metrics.is_reflect_session("Just refactor my code")
    assert not metrics.is_reflect_session(None)
    # Substring without word boundary doesn't match (the slash itself enforces boundary).
    assert not metrics.is_reflect_session("reflect-agent-sessions without slash")


def test_detect_retry_loops_finds_repeated_actions():
    same_input = {"command": "ls foo"}
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Bash", "input": same_input},
                ]
            },
        }
        for _ in range(5)
    ]
    assert metrics.detect_retry_loops(events, window=4) >= 1


def test_detect_retry_loops_returns_zero_for_diverse():
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Bash", "input": {"command": f"cmd-{i}"}},
                ]
            },
        }
        for i in range(5)
    ]
    assert metrics.detect_retry_loops(events) == 0


def test_derive_outcome_end_turn():
    events = [
        {"type": "user", "message": {"content": "hi"}},
        {"type": "assistant", "message": {"stop_reason": "end_turn"}},
    ]
    assert metrics.derive_outcome(events) == "task_completed"


def test_derive_outcome_errored_out():
    err = {
        "type": "user",
        "message": {
            "content": [
                {"type": "tool_result", "is_error": True, "content": "oops"},
            ]
        },
    }
    events = [err, err, err]
    assert metrics.derive_outcome(events) == "errored_out"


def test_derive_outcome_user_terminated():
    events = [
        {"type": "assistant", "message": {"stop_reason": "end_turn"}},
        {"type": "user", "message": {"content": "stop please"}, "isMeta": False},
    ]
    assert metrics.derive_outcome(events) == "user_terminated"
