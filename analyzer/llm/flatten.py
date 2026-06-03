"""Stage [3] — Opus full-flatten on the top-K most "interesting" sessions.

Invokes `claude -p` via subprocess for subscription billing (zero marginal cost
on Opus). Falls back to AsyncAnthropic with ANTHROPIC_API_KEY when subscription
quota is exhausted AND `--api-key-fallback` was passed.
"""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
import time
from typing import Any

from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .. import audit, config
from ..subprocess_util import run_external
from . import prompt_loader
from .schemas import OpusFindings

_TRUNCATE_THINKING = 200
_TRUNCATE_TOOL_RESULT = 600
_TRUNCATE_TOOL_INPUT = 800

# Budget calibrated for Opus 1M context window with Cyrillic-heavy prompts:
#   BPE tokenizes non-ASCII chars 1:2-3 (each Cyrillic glyph = 2-3 tokens),
#   so 700 KB of mixed Cyrillic+ASCII text ≈ 200-300 K tokens. Add ~50K for
#   system prompt + CLAUDE.md auto-load → ~350K total, well under 1M context.
#   Empirically confirmed: e2e dogfood run with prompt size 697,250 B (700 KB)
#   completed successfully on Opus.
_PROMPT_BUDGET_BYTES = 700 * 1024


def _turn_from_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert raw events to a turn-based view for prompt rendering."""
    turns: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for e in events:
        t = e.get("type")
        msg = e.get("message") or {}
        if t == "user" and not e.get("isMeta"):
            if current is not None:
                turns.append(current)
            user_text = ""
            content = msg.get("content")
            if isinstance(content, str):
                # Could be raw text or JSON-encoded list.
                try:
                    decoded = json.loads(content)
                except json.JSONDecodeError:
                    user_text = content
                else:
                    if isinstance(decoded, str):
                        user_text = decoded
                    elif isinstance(decoded, list):
                        # Collect text blocks; tool_result also lives here.
                        for b in decoded:
                            if isinstance(b, dict) and b.get("type") == "text":
                                user_text = b.get("text", "")
                                break
                            if isinstance(b, dict) and b.get("type") == "tool_result":
                                payload = b.get("content")
                                if current is not None:
                                    current["tool_results"].append(
                                        {
                                            "is_error": bool(b.get("is_error")),
                                            "content": _truncate(
                                                _stringify(payload), _TRUNCATE_TOOL_RESULT
                                            ),
                                        }
                                    )
                        # If this event is purely tool_result, do not start a new turn.
                        if not user_text:
                            continue
            current = {
                "user_text": user_text[:1000],
                "thinking": [],
                "assistant_text": "",
                "tool_uses": [],
                "tool_results": [],
            }
        elif t == "assistant" and current is not None:
            content = msg.get("content")
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except json.JSONDecodeError:
                    content = []
            if not isinstance(content, list):
                content = []
            for b in content:
                if not isinstance(b, dict):
                    continue
                btype = b.get("type")
                if btype == "thinking":
                    th = b.get("thinking", "")
                    if th:
                        current["thinking"].append(_truncate(th, _TRUNCATE_THINKING))
                elif btype == "text":
                    txt = b.get("text", "")
                    if txt:
                        current["assistant_text"] = (
                            current["assistant_text"] + "\n" + txt
                        ).strip()[:1500]
                elif btype == "tool_use":
                    current["tool_uses"].append(
                        {
                            "name": b.get("name", "?"),
                            "input": _truncate(_stringify(b.get("input")), _TRUNCATE_TOOL_INPUT),
                        }
                    )

    if current is not None:
        turns.append(current)
    return turns


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return repr(value)


def _truncate(text: str, n: int) -> str:
    if len(text) <= n:
        return text
    return text[:n] + " ...[truncated]"


def _enrich_session_for_prompt(
    session: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    enriched = dict(session)
    enriched["turns"] = _turn_from_events(events)
    enriched["total_tokens"] = session.get("max_input_tokens", 0) + session.get(
        "total_output_tokens", 0
    )
    return enriched


def _render_user_prompt(sessions: list[dict[str, Any]], dev_id: str, proj_id: str) -> str:
    return prompt_loader.render(
        "top_k_opus_user.j2",
        sessions=sessions,
        dev_id=dev_id,
        proj_id=proj_id,
    )


def _shrink_session(s: dict[str, Any]) -> dict[str, Any]:
    """Keep only first 15% + last 15% of turns and drop thinking blocks."""
    turns = s.get("turns") or []
    if len(turns) < 6:
        keep = turns
    else:
        head = max(1, int(len(turns) * 0.15))
        tail = max(1, int(len(turns) * 0.15))
        keep = turns[:head] + turns[-tail:]
    shrunk_turns = []
    for t in keep:
        copy = dict(t)
        copy["thinking"] = []
        copy["tool_uses"] = [
            {**tu, "input": _truncate(tu.get("input", ""), 200)} for tu in t.get("tool_uses", [])
        ]
        copy["tool_results"] = [
            {**tr, "content": _truncate(tr.get("content", ""), 200)}
            for tr in t.get("tool_results", [])
        ]
        shrunk_turns.append(copy)
    out = dict(s)
    out["turns"] = shrunk_turns
    return out


_MIN_SESSION_BYTES = 4 * 1024


def _fit_session_to_budget(
    s: dict[str, Any], dev_id: str, proj_id: str, budget: int
) -> tuple[dict[str, Any], bool]:
    """Shrink/trim one session so its rendered size ≤ `budget`, never dropping it.

    PF-27: replaces whole-session drop with chunking so every top-K session
    stays represented. Returns ``(session, chunked)`` where ``chunked`` is True
    when any reduction was applied. Strategy: within budget → unchanged; else
    apply the head+tail ``_shrink_session``; if still over, drop the middle-most
    turn repeatedly (keeping head and tail) until it fits or 2 turns remain.
    """
    if len(_render_user_prompt([s], dev_id, proj_id).encode("utf-8")) <= budget:
        return s, False
    s = _shrink_session(s)
    turns = s.get("turns") or []
    while len(turns) > 2 and (
        len(_render_user_prompt([{**s, "turns": turns}], dev_id, proj_id).encode("utf-8")) > budget
    ):
        mid = len(turns) // 2
        turns = turns[:mid] + turns[mid + 1 :]
    return {**s, "turns": turns}, True


def _chunk_sessions_to_budget(
    sessions: list[dict[str, Any]], dev_id: str, proj_id: str, budget: int
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fair-share chunk every session so the combined prompt fits `budget`
    without dropping any session (PF-27).

    Each session gets an equal slice (``budget // n``, floored at
    ``_MIN_SESSION_BYTES``) and is shrunk/trimmed to fit it. Returns
    ``(fitted_sessions, chunked_sids)`` — the 8-char ids of sessions that were
    reduced, for audit warnings.
    """
    if not sessions:
        return sessions, []
    share = max(_MIN_SESSION_BYTES, budget // max(1, len(sessions)))
    fitted: list[dict[str, Any]] = []
    chunked: list[str] = []
    for s in sessions:
        s2, was_chunked = _fit_session_to_budget(s, dev_id, proj_id, share)
        if was_chunked:
            chunked.append(str(s.get("sessionId", "?"))[:8])
        fitted.append(s2)
    return fitted, chunked


class OpusInvocationError(RuntimeError):
    """Raised when `claude -p` fails. Set `is_quota=True` for fall-back path."""

    def __init__(self, message: str, *, is_quota: bool = False) -> None:
        super().__init__(message)
        self.is_quota = is_quota


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    retry=retry_if_exception_type(OpusInvocationError),
    reraise=True,
)
def _call_claude_subprocess(
    system_prompt: str, user_prompt: str, model: str, timeout_s: int = 180
) -> str:
    """Invoke `claude -p` subprocess for subscription-billed Opus call.

    Billing path is enforced via explicit env construction:
      1. Strip `ANTHROPIC_API_KEY` from subprocess env — with it set, the CLI
         would silently bill the API key instead of subscription.
      2. Set `CLAUDE_CODE_OAUTH_TOKEN` from 1P (long-life OAuth token for
         subscription). Auth becomes deterministic and doesn't depend on the
         user's keychain state (works in CI / isolated dev env / fresh machines).

    Other isolation flags (we deliberately do NOT pass `--bare`, because it
    forces ANTHROPIC_API_KEY auth and bypasses OAuth):
      - `--tools ""`               — no tools, no Bash side-effects.
      - `--disable-slash-commands` — prevent /reflect or other skills from
                                     being re-triggered inside the subprocess.
      - `--no-session-persistence` — don't write transcript.
      - `--output-format json`     — deterministic envelope for parsing.

    Stage [4]/[5] Haiku uses an explicit `api_key=…` kwarg to AsyncAnthropic;
    it ignores env entirely (see `mapreduce._client_kwargs()`).
    """
    from .. import auth as _auth

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(user_prompt)
        prompt_file = pathlib.Path(f.name)

    subprocess_env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    oauth_token = subprocess_env.get("CLAUDE_CODE_OAUTH_TOKEN") or _auth.read_oauth_token()
    if oauth_token:
        subprocess_env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token
    # If neither env nor 1P has an OAuth token, `claude -p` falls back to
    # whatever keychain auth exists — best-effort. analyzer-cli --check has
    # already verified `claude_cli` works; stderr surfaces a clear error
    # if auth is unusable.

    # Run from an isolated cwd with no project CLAUDE.md / settings.json /
    # hooks → claude -p only auto-loads the user-global ~/.claude/CLAUDE.md
    # (small, expected, OAuth-cacheable). This avoids context bloat from the
    # current project's CLAUDE.md (which can be 200+ LoC) eating into the 1M
    # context window for our user prompt.
    isolated_cwd = tempfile.mkdtemp(prefix="agent-reflect-claude-p-")
    try:
        with prompt_file.open("rb") as stdin_fp:
            res = run_external(
                [
                    "claude",
                    "-p",
                    "--model",
                    model,
                    "--system-prompt",
                    system_prompt,
                    "--tools",
                    "",
                    "--disable-slash-commands",
                    "--no-session-persistence",
                    "--output-format",
                    "json",
                    "--permission-mode",
                    "bypassPermissions",
                ],
                timeout=timeout_s,
                env=subprocess_env,
                cwd=isolated_cwd,
                stdin=stdin_fp,
                check=False,
            )
    except RuntimeError as e:
        # run_external raises on timeout or a missing `claude` executable.
        raise OpusInvocationError(f"claude -p invocation failed: {e}") from e
    finally:
        prompt_file.unlink(missing_ok=True)
        try:
            pathlib.Path(isolated_cwd).rmdir()
        except OSError:
            pass

    if res.returncode != 0:
        # When stderr is empty, claude -p may have written the error envelope
        # to stdout instead (e.g. context-window overflow surfaces there).
        # Include first 400ch of stdout in the error so callers can see it.
        stderr_lc = (res.stderr or "").lower()
        stdout_lc = (res.stdout or "").lower()
        combined_lc = stderr_lc + " " + stdout_lc
        if "rate limit" in combined_lc or "quota" in combined_lc or "exceeded" in combined_lc:
            raise OpusInvocationError(
                f"quota_exhausted: stderr={res.stderr[:200]} stdout={res.stdout[:200]}",
                is_quota=True,
            )
        raise OpusInvocationError(
            f"claude -p exit {res.returncode}: "
            f"stderr={res.stderr[:200]!r} stdout={res.stdout[:400]!r}"
        )

    # Parse the JSON envelope from --output-format json.
    try:
        env = json.loads(res.stdout)
    except json.JSONDecodeError:
        return res.stdout
    if isinstance(env, dict):
        # Newer envelope: { "result": "<text>", ... }
        if isinstance(env.get("result"), str):
            return env["result"]
        # Older variant: { "content": [...], "role": "assistant" }
        content = env.get("content")
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and isinstance(b.get("text"), str):
                    return b["text"]
    return res.stdout


def _call_anthropic_fallback(
    system_prompt: str, user_prompt: str, model: str, timeout_s: int = 240
) -> str:
    """Fallback to direct API when subscription Opus is exhausted.

    Bounded by `timeout_s` (default 240s, matching `_call_claude_subprocess`)
    via the Anthropic SDK's per-request timeout — without this the call could
    hang and break the retry budget (tenacity expects bounded execution).

    `api_key=…` passed explicitly so we don't depend on env state (parent
    process may have ANTHROPIC_API_KEY unset or different from 1P's value).
    """
    from anthropic import Anthropic, APITimeoutError

    from .. import auth as _auth

    api_key = _auth.read_anthropic_api_key()
    if not api_key:
        raise OpusInvocationError("anthropic fallback: ANTHROPIC_API_KEY unavailable")
    client = Anthropic(api_key=api_key, timeout=float(timeout_s))
    try:
        msg = client.messages.create(
            model=model,
            max_tokens=8000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except APITimeoutError as e:
        raise OpusInvocationError(f"anthropic fallback timeout after {timeout_s}s") from e
    parts = [b.text for b in msg.content if hasattr(b, "text") and b.text]
    return "\n".join(parts)


def analyze_top_k(
    *,
    sessions: list[dict[str, Any]],
    events_by_session: dict[str, list[dict[str, Any]]],
    dev_id: str,
    proj_id: str,
    since: str,
    model: str,
    record: audit.RunRecord,
    api_key_fallback: bool,
) -> OpusFindings:
    """Stage [3] entry point."""
    if not sessions:
        return OpusFindings(findings=[])

    enriched = [
        _enrich_session_for_prompt(s, events_by_session.get(s["sessionId"], [])) for s in sessions
    ]
    system_prompt = prompt_loader.render(
        "top_k_opus_system.j2",
        n_sessions=len(sessions),
        since=since,
    )
    # Fit the user prompt into the Opus context window:
    #   1. Fair-share chunking — give each session an equal slice of the budget
    #      and shrink/trim it to fit, so NO session is dropped (PF-27). The most
    #      active sessions used to be dropped wholesale (opus_input_tok=0).
    #   2. Hard-truncate the final rendered string to the budget — last resort
    #      so Opus always receives a parseable payload, even if it's partial.
    rendered_sessions = list(enriched)
    user_prompt = _render_user_prompt(rendered_sessions, dev_id, proj_id)
    if len(user_prompt.encode("utf-8")) > _PROMPT_BUDGET_BYTES:
        rendered_sessions, chunked_sids = _chunk_sessions_to_budget(
            rendered_sessions, dev_id, proj_id, _PROMPT_BUDGET_BYTES
        )
        for sid in chunked_sids:
            record.warnings.append(f"opus_session_chunked sid={sid}")
        user_prompt = _render_user_prompt(rendered_sessions, dev_id, proj_id)
    if len(user_prompt.encode("utf-8")) > _PROMPT_BUDGET_BYTES:
        # Hard cap — slice the encoded bytes, decode loosely. Truncates mid-turn
        # but Opus still gets the start of the flattened sessions and the
        # system-prompt-defined schema instructions are sufficient to extract
        # patterns from a partial sample.
        truncated_bytes = user_prompt.encode("utf-8")[:_PROMPT_BUDGET_BYTES]
        user_prompt = truncated_bytes.decode("utf-8", errors="ignore") + "\n[...truncated]\n"
        record.warnings.append(f"opus_prompt_hard_truncated size={len(user_prompt):,}B")

    started = time.time()
    raw: str = ""
    try:
        raw = _call_claude_subprocess(system_prompt, user_prompt, model=_resolve_model(model))
    except OpusInvocationError as e:
        # Only fall back to API key on confirmed quota exhaustion. Other failures
        # (timeout, bad flag, parse error) shouldn't silently swap subscription→API
        # billing — that would surprise the user with unexpected charges.
        if e.is_quota and api_key_fallback and os.environ.get("ANTHROPIC_API_KEY"):
            record.warnings.append(f"opus_subscription_quota_exhausted_falling_back: {e}")
            try:
                raw = _call_anthropic_fallback(
                    system_prompt, user_prompt, model=_resolve_model(model)
                )
            except OpusInvocationError as e2:
                record.warnings.append(f"opus_fallback_failed: {e2}")
                return OpusFindings(findings=[])
        else:
            record.warnings.append(f"opus_failed: {e}")
            return OpusFindings(findings=[])
    except RetryError as e:
        record.warnings.append(f"opus_retry_exhausted: {e}")
        return OpusFindings(findings=[])
    finally:
        record.opus_wall_s = round(time.time() - started, 2)

    try:
        payload = prompt_loader.extract_json(raw)
        return OpusFindings.model_validate_json(payload)
    except Exception as e:  # pragma: no cover - defensive
        record.warnings.append(f"opus_parse_failed: {type(e).__name__}: {str(e)[:200]}")
        return OpusFindings(findings=[])


def _resolve_model(alias_or_full: str) -> str:
    """Accept `opus` / `sonnet` / `haiku` aliases or full model IDs."""
    aliases = {
        "opus": config.DEFAULT_OPUS_MODEL,
        "sonnet": "claude-sonnet-4-6",
        "haiku": config.DEFAULT_HAIKU_MODEL,
    }
    return aliases.get(alias_or_full, alias_or_full)
