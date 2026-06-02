"""Stage [4] — Haiku map-reduce summaries with semaphore-bounded concurrency.

Each session is reduced to an 8K-token compact representation, then sent in
parallel via AsyncAnthropic. Semaphore cap defaults to 10 (API rate-limit
driven, not subscription).
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from typing import Any

from .. import audit, metrics
from . import flatten, prompt_loader
from .schemas import HaikuSummary


def _build_compact_session(session: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive the per-session compact representation rendered into the user prompt."""
    tool_counts: Counter = Counter()
    thinking_first = thinking_last = ""
    for e in events:
        if e.get("type") != "assistant":
            continue
        msg = e.get("message") or {}
        content = msg.get("content")
        if isinstance(content, str):
            try:
                import json as _json
                content = _json.loads(content)
            except Exception:
                content = []
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                tool_counts[b.get("name", "?")] += 1
            elif b.get("type") == "thinking":
                th = b.get("thinking", "")
                if th:
                    if not thinking_first:
                        thinking_first = th[:200]
                    thinking_last = th[:200]

    outcome = metrics.derive_outcome(events)
    return {
        "sessionId": session["sessionId"],
        "first_user_prompt": session.get("first_user_prompt", "")[:800] or "<empty>",
        "started_at": session.get("started_at") or "",
        "tool_counts": dict(tool_counts.most_common(8)),
        "error_classes": session.get("error_classes", []) or ["<none>"],
        "thinking_digest": (
            thinking_first + (" ... " + thinking_last if thinking_last else "")
        ) or "<none>",
        "last_assistant_text": session.get("last_assistant_text", "")[:600] or "<none>",
        "outcome": outcome,
    }


async def _summarize_one(
    session: dict[str, Any],
    events: list[dict[str, Any]],
    dev_id: str,
    proj_id: str,
    client,
    sem: asyncio.Semaphore,
    model: str,
    record: audit.RunRecord,
) -> HaikuSummary | None:
    async with sem:
        try:
            user_prompt = prompt_loader.render(
                "haiku_summary_user.j2",
                session=_build_compact_session(session, events),
                dev_id=dev_id,
                proj_id=proj_id,
            )
            system_prompt = prompt_loader.render("haiku_summary_system.j2")
            msg = await client.messages.create(
                model=flatten._resolve_model(model),
                max_tokens=1500,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text_blocks = [b.text for b in msg.content if hasattr(b, "text") and b.text]
            raw = "\n".join(text_blocks)
            payload = prompt_loader.extract_json(raw)
            summary = HaikuSummary.model_validate_json(payload)
            # Enforce session_id from input (model may halucinate).
            summary.session_id = session["sessionId"]
            record.haiku_summaries_completed += 1
            return summary
        except Exception as e:
            record.haiku_summaries_failed += 1
            record.warnings.append(
                f"haiku_summary_failed sid={session.get('sessionId','?')}: "
                f"{type(e).__name__}: {str(e)[:120]}"
            )
            return None


async def _map_rest_async(
    rest: list[dict[str, Any]],
    events_by_session: dict[str, list[dict[str, Any]]],
    dev_id: str,
    proj_id: str,
    model: str,
    concurrency: int,
    record: audit.RunRecord,
) -> list[HaikuSummary]:
    from anthropic import AsyncAnthropic
    from .. import auth as _auth
    api_key = _auth.read_anthropic_api_key()
    # Explicit api_key — don't depend on env (parent process may have it unset
    # or set to a different account). Falls back to env-discovery only if 1P
    # is unreachable and env happens to have a key.
    client = AsyncAnthropic(api_key=api_key) if api_key else AsyncAnthropic()
    sem = asyncio.Semaphore(max(1, concurrency))
    tasks = [
        asyncio.create_task(
            _summarize_one(
                s, events_by_session.get(s["sessionId"], []),
                dev_id, proj_id, client, sem, model, record,
            )
        )
        for s in rest
    ]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return [r for r in results if r is not None]


def map_rest(
    *,
    rest: list[dict[str, Any]],
    events_by_session: dict[str, list[dict[str, Any]]],
    dev_id: str,
    proj_id: str,
    model: str,
    concurrency: int,
    record: audit.RunRecord,
) -> list[HaikuSummary]:
    """Sync entry point for Stage [4]. Returns successful summaries only."""
    if not rest:
        return []
    started = time.time()
    try:
        result = asyncio.run(
            _map_rest_async(rest, events_by_session, dev_id, proj_id, model, concurrency, record)
        )
    finally:
        record.haiku_wall_s = round(time.time() - started, 2)
    return result
