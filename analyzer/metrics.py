"""Per-session metrics + ranking + heuristics used by the LLM pipeline."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any


def is_reflect_session(first_user_prompt: str | None) -> bool:
    """Drop sessions whose first user prompt invoked /reflect-agent-sessions
    (PRD §C3 — prevents self-pollution of the analysis corpus)."""
    if not first_user_prompt:
        return False
    return bool(re.search(r"/reflect-agent-sessions\b", first_user_prompt))


def interestingness_score(session: dict[str, Any]) -> float:
    """Empirical weights — calibrate in Step 6 spike.

    Heuristic mix prioritising:
      • sessions with errors (Most likely to surface failure modes).
      • sessions with retry loops (action repetition is a MAST SI-1.3 signal).
      • high tool-use churn (more events → more chance of structural bugs).
      • large output (long sessions tend to contain more actionable patterns).
    """
    errors = float(session.get("errors", 0))
    retry_loops = float(session.get("retry_loops", 0))
    tool_calls = float(session.get("tool_calls", 0))
    total_out = float(session.get("total_output_tokens", 0))
    diversity = float(session.get("tool_diversity", 0))

    return (
        errors * 3.0
        + retry_loops * 5.0
        + 0.5 * (total_out / 1000.0)
        + 0.2 * tool_calls
        + 0.3 * diversity
    )


def detect_retry_loops(events: list[dict[str, Any]], window: int = 4) -> int:
    """N-gram detection on (tool_name, hash(input)) sequence.

    Counts occurrences where the same `(tool_name, input_hash)` pair appears
    ≥3 times within a sliding window of size `window`. Inspired by
    Majgaonkar et al. arXiv:2511.00197 — action-sequence repetition as a
    proxy for stuck-in-loop trajectories.
    """
    actions: list[tuple[str, str]] = []
    for e in events:
        if e.get("type") != "assistant":
            continue
        msg = e.get("message") or {}
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            name = b.get("name") or ""
            payload = b.get("input")
            payload_repr = repr(payload)[:300]
            # SHA-256 fingerprint for loop detection only — not cryptographic.
            h = hashlib.sha256(payload_repr.encode("utf-8")).hexdigest()[:12]
            actions.append((name, h))

    if len(actions) < 3:
        return 0

    loops = 0
    for i in range(len(actions) - window + 1):
        windowed = actions[i : i + window]
        counts = Counter(windowed)
        if counts.most_common(1)[0][1] >= 3:
            loops += 1
    return loops


def derive_outcome(events: list[dict[str, Any]]) -> str:
    """Heuristic outcome label per PRD §C4 schema.

    Returns one of: task_completed | task_abandoned | errored_out | user_terminated.
    """
    if not events:
        return "task_abandoned"

    last_3 = events[-3:]
    errors_in_tail = sum(
        1
        for e in last_3
        if e.get("type") == "user"
        and any(
            (b.get("type") == "tool_result" and b.get("is_error"))
            for b in (e.get("message") or {}).get("content", [])
            if isinstance(b, dict)
        )
    )
    if errors_in_tail >= 2:
        return "errored_out"

    last = events[-1]
    if last.get("type") == "user" and not last.get("isMeta"):
        return "user_terminated"

    if last.get("type") == "assistant":
        msg = last.get("message") or {}
        if msg.get("stop_reason") == "end_turn":
            return "task_completed"

    return "task_abandoned"
