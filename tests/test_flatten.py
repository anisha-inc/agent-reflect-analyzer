"""Tests for analyzer.llm.flatten — fair-share chunking (PF-27).

Large sessions used to be dropped wholesale when the Opus prompt overflowed the
budget (opus_input_tok=0). Chunking shrinks/trims each session to an equal slice
of the budget so every top-K session stays represented.
"""

from __future__ import annotations

from analyzer.llm import flatten


def _turn(text: str) -> dict:
    return {
        "user_text": text,
        "thinking": [],
        "assistant_text": "",
        "tool_uses": [],
        "tool_results": [],
    }


def _session(sid: str, n_turns: int, text_len: int) -> dict:
    return {
        "sessionId": sid,
        "started_at": "2026-06-01T00:00:00Z",
        "total_tokens": 1000,
        "errors": 0,
        "turns": [_turn("x" * text_len) for _ in range(n_turns)],
    }


def test_fit_under_budget_returns_unchanged():
    s = _session("s", n_turns=2, text_len=50)
    out, chunked = flatten._fit_session_to_budget(s, "dev", "proj", budget=100_000)
    assert chunked is False
    assert out is s


def test_fit_over_budget_chunks_without_dropping_session():
    s = _session("s", n_turns=30, text_len=2000)
    out, chunked = flatten._fit_session_to_budget(s, "dev", "proj", budget=6_000)
    assert chunked is True
    assert out["sessionId"] == "s"
    rendered = flatten._render_user_prompt([out], "dev", "proj")
    # Trimmed to fit, or hit the 2-turn floor (never dropped to nothing).
    assert len(rendered.encode("utf-8")) <= 6_000 or len(out["turns"]) == 2


def test_chunk_keeps_all_sessions_and_fits_budget():
    sessions = [_session(f"sess-{i}", n_turns=30, text_len=2000) for i in range(3)]
    budget = 20_000  # small budget to force chunking on every session

    fitted, chunked = flatten._chunk_sessions_to_budget(sessions, "dev", "proj", budget)

    # PF-27: every session is still present (none dropped).
    assert [s["sessionId"] for s in fitted] == ["sess-0", "sess-1", "sess-2"]
    assert sorted(chunked) == ["sess-0", "sess-1", "sess-2"]

    rendered = flatten._render_user_prompt(fitted, "dev", "proj")
    # Each session ≤ budget//3 share ⇒ combined ≤ budget (+ small loop overhead).
    assert len(rendered.encode("utf-8")) <= budget + 1024
    # And every session id is visible in the final prompt.
    for sid in ("sess-0", "sess-1", "sess-2"):
        assert sid in rendered


def test_chunk_empty_is_noop():
    fitted, chunked = flatten._chunk_sessions_to_budget([], "dev", "proj", 10_000)
    assert fitted == []
    assert chunked == []
