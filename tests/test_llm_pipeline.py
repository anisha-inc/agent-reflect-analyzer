"""Tests for analyzer.llm.{pipeline, flatten, mapreduce, clio, prompt_loader}."""

from __future__ import annotations

from analyzer import audit
from analyzer.llm import clio, flatten, mapreduce, pipeline, prompt_loader
from analyzer.llm.schemas import Candidate, ClusterFinding, Finding, OpusFindings


def test_extract_json_pure():
    assert prompt_loader.extract_json('{"a":1}') == '{"a":1}'


def test_extract_json_fenced():
    text = '```json\n{"a": 1, "b": 2}\n```'
    assert '"a"' in prompt_loader.extract_json(text)


def test_extract_json_embedded():
    text = 'Here you go:\n{\n  "a": 1\n}\nDone.'
    out = prompt_loader.extract_json(text)
    assert out.startswith("{") and out.endswith("}")


def test_extract_json_balanced_nested_braces():
    """Nested {} inside the JSON value must not be truncated."""
    text = 'prelude {"outer": {"inner": 1}, "k": "v"} suffix'
    out = prompt_loader.extract_json(text)
    assert out == '{"outer": {"inner": 1}, "k": "v"}'


def test_extract_json_balanced_stops_at_first_object():
    """Two top-level objects in prose: take the first, ignore the second."""
    text = 'first {"a": 1} then {"b": 2}'
    out = prompt_loader.extract_json(text)
    assert out == '{"a": 1}'
    # Crucially: NOT greedy capture across both — that would be invalid JSON.
    import json as _json

    _json.loads(out)


def test_extract_json_balanced_handles_string_with_brace():
    """`}` inside a string literal must not close the object."""
    text = '{"msg": "looks like }"}'
    out = prompt_loader.extract_json(text)
    assert out == '{"msg": "looks like }"}'


def test_extract_json_balanced_handles_escaped_quote():
    text = r'{"q": "say \"hi\"", "n": 1}'
    out = prompt_loader.extract_json(text)
    assert out == r'{"q": "say \"hi\"", "n": 1}'


def test_truncate_short_strings_unchanged():
    assert flatten._truncate("hi", 10) == "hi"


def test_truncate_long_strings_marked():
    long = "x" * 100
    out = flatten._truncate(long, 20)
    assert out.endswith("...[truncated]")
    assert out.startswith("x" * 20)


def test_turn_from_events_simple_user_then_assistant():
    events = [
        {"type": "user", "message": {"role": "user", "content": "do thing"}},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "Let me think"},
                    {"type": "text", "text": "ok"},
                    {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
                ],
            },
        },
    ]
    turns = flatten._turn_from_events(events)
    assert len(turns) == 1
    t = turns[0]
    assert t["user_text"] == "do thing"
    assert t["assistant_text"] == "ok"
    assert t["thinking"] == ["Let me think"]
    assert t["tool_uses"][0]["name"] == "Bash"


def test_mapreduce_build_compact_extracts_tool_counts():
    session = {
        "sessionId": "abc",
        "first_user_prompt": "Fix the bug",
        "last_assistant_text": "Done.",
        "error_classes": ["TypeError"],
        "started_at": "2026-05-25T10:00:00Z",
    }
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {}},
                    {"type": "tool_use", "name": "Read", "input": {}},
                    {"type": "tool_use", "name": "Edit", "input": {}},
                    {"type": "thinking", "thinking": "Looking at the code"},
                ]
            },
        },
    ]
    compact = mapreduce._build_compact_session(session, events)
    assert compact["sessionId"] == "abc"
    assert compact["tool_counts"]["Read"] == 2
    assert compact["tool_counts"]["Edit"] == 1
    assert "Looking" in compact["thinking_digest"]


def test_clio_cluster_count_grows_with_size():
    assert clio._cluster_count(10) == 3
    assert clio._cluster_count(50) == 10
    assert clio._cluster_count(500) == 15  # clamped


def test_pipeline_merge_dedups_overlapping_pattern_ids():
    opus = OpusFindings(
        findings=[
            Finding(
                pattern_id="foo-bar",
                title="Foo",
                severity="low",
                frequency_in_sample=3,
                session_examples=[],
                mast_taxonomy="OTHER",
                symptom="",
                proposed_fix="",
                evidence_quotes=[],
            ),
        ]
    )
    clusters = [
        ClusterFinding(name="Foo bar", description="", frequency=5, session_ids=[]),
    ]
    merged = pipeline._merge(opus, clusters)
    # Slug from cluster "Foo bar" → "foo-bar" matches opus pattern_id.
    assert len(merged) == 1
    assert merged[0].frequency == 3 + 5


def test_pipeline_filter_min_freq():
    candidates = [
        Candidate(
            source="opus_top_k",
            pattern_id="p1",
            title="t1",
            frequency=1,
            symptom="s",
            proposed_fix="f",
        ),
        Candidate(
            source="opus_top_k",
            pattern_id="p2",
            title="t2",
            frequency=2,
            symptom="s",
            proposed_fix="f",
        ),
        Candidate(
            source="cluster",
            pattern_id="p3",
            title="t3",
            frequency=2,
            symptom="s",
            proposed_fix="f",
        ),
        Candidate(
            source="cluster",
            pattern_id="p4",
            title="t4",
            frequency=3,
            symptom="s",
            proposed_fix="f",
        ),
    ]
    out = pipeline._filter_min_freq(candidates)
    ids = {c.pattern_id for c in out}
    assert ids == {"p2", "p4"}


def test_pipeline_returns_empty_on_no_sessions():
    record = audit.RunRecord()
    out = pipeline.run(
        sessions=[],
        events_by_session={},
        top_k=10,
        model_top_k="opus",
        model_rest="haiku",
        concurrency=10,
        cluster=False,
        api_key_fallback=False,
        record=record,
        strategy="hybrid",
        since="7d",
    )
    assert out == []


def test_prompt_render_haiku_user_renders():
    out = prompt_loader.render(
        "haiku_summary_user.j2",
        session={
            "sessionId": "abc",
            "first_user_prompt": "do thing",
            "started_at": "2026-05-25",
            "tool_counts": {"Read": 3, "Bash": 1},
            "error_classes": ["TypeError"],
            "thinking_digest": "Looking",
            "last_assistant_text": "Done.",
            "outcome": "task_completed",
        },
        dev_id="d",
        proj_id="p",
    )
    assert "SESSION abc" in out
    assert "Read(3)" in out
    assert "task_completed" in out


def test_resolve_model_aliases():
    assert flatten._resolve_model("opus").startswith("claude-opus")
    assert flatten._resolve_model("haiku").startswith("claude-haiku")
    assert flatten._resolve_model("sonnet").startswith("claude-sonnet")
    # Pass-through for non-aliases.
    assert flatten._resolve_model("claude-haiku-4-5-20251001") == "claude-haiku-4-5-20251001"


def test_stringify_handles_dicts_and_none():
    assert flatten._stringify(None) == ""
    assert flatten._stringify("foo") == "foo"
    assert "key" in flatten._stringify({"key": "val"})


def test_turn_from_events_collects_thinking_blocks():
    events = [
        {"type": "user", "message": {"role": "user", "content": "hi"}},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "First thought"},
                    {"type": "thinking", "thinking": "Second thought"},
                    {"type": "text", "text": "done"},
                ],
            },
        },
    ]
    turns = flatten._turn_from_events(events)
    assert len(turns) == 1
    assert turns[0]["thinking"] == ["First thought", "Second thought"]


def test_pipeline_skip_opus_when_strategy_map_reduce_only():
    """strategy=map-reduce-B should skip Stage [3]."""
    from unittest.mock import patch

    import analyzer.llm.flatten as flatten_mod

    sessions = [
        {
            "sessionId": "s1",
            "tool_calls": 0,
            "errors": 0,
            "total_output_tokens": 0,
            "tool_diversity": 0,
            "score": 0,
        }
    ]
    record = audit.RunRecord()
    with (
        patch.object(flatten_mod, "analyze_top_k") as opus,
        patch("analyzer.llm.mapreduce.map_rest", return_value=[]),
    ):
        pipeline.run(
            sessions=sessions,
            events_by_session={"s1": []},
            top_k=0,
            model_top_k="opus",
            model_rest="haiku",
            concurrency=3,
            cluster=False,
            api_key_fallback=False,
            record=record,
            strategy="map-reduce-B",
            since="7d",
        )
    opus.assert_not_called()


def test_pipeline_strategy_flatten_A_skips_haiku():
    from unittest.mock import patch

    record = audit.RunRecord()
    sessions = [
        {
            "sessionId": "s1",
            "tool_calls": 0,
            "errors": 0,
            "total_output_tokens": 0,
            "tool_diversity": 0,
            "score": 0,
        }
    ]
    with (
        patch("analyzer.llm.flatten.analyze_top_k") as opus,
        patch("analyzer.llm.mapreduce.map_rest") as haiku,
    ):
        opus.return_value = OpusFindings()
        pipeline.run(
            sessions=sessions,
            events_by_session={"s1": []},
            top_k=10,
            model_top_k="opus",
            model_rest="haiku",
            concurrency=3,
            cluster=False,
            api_key_fallback=False,
            record=record,
            strategy="flatten-A",
            since="7d",
        )
    haiku.assert_not_called()
