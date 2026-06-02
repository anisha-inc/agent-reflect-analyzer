"""Jinja2 template loader + small helpers shared by stages."""

from __future__ import annotations

import functools
import json
import pathlib
import re

from jinja2 import Environment, FileSystemLoader, StrictUndefined

PROMPT_DIR = pathlib.Path(__file__).parent / "prompts"


@functools.lru_cache(maxsize=1)
def _env() -> Environment:
    # Output is plain text used as `claude -p` / API user prompts, not HTML —
    # autoescape would break model output (escape angle brackets in code).
    # nosemgrep: python.flask.security.xss.audit.direct-use-of-jinja2.direct-use-of-jinja2
    return Environment(
        loader=FileSystemLoader(str(PROMPT_DIR)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=False,
        autoescape=False,  # noqa: S701 — markdown/text prompt output, no HTML/XSS surface
    )


def render(name: str, **kwargs) -> str:
    # Same rationale as _env() above — markdown / text output, no XSS surface.
    # nosemgrep: python.flask.security.xss.audit.direct-use-of-jinja2.direct-use-of-jinja2
    return _env().get_template(name).render(**kwargs)


_FENCE_OPEN_RE = re.compile(r"```(?:json)?\s*", re.I)


def _find_balanced_json(text: str, start: int = 0) -> str | None:
    """Return the first **balanced** `{...}` substring at or after `start`.

    Tracks string literals and `\\`-escapes so braces inside `"…"` and escaped
    quotes don't break depth counting. Returns the matched substring, or None
    if no balanced object is found.

    Previous impl used a greedy `\\{.*\\}` regex which captured from the first
    `{` to the LAST `}` — wrong when the model returns `{json} prose {extra}`,
    where we want only `{json}`. Non-greedy `\\{.*?\\}` is also wrong because
    it stops at the first `}`, breaking on nested JSON. Balanced parsing is
    the correct approach (CodeRabbit suggestion on PR #45).
    """
    n = len(text)
    i = start
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        in_string = False
        escape = False
        for j in range(i, n):
            ch = text[j]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[i : j + 1]
        # Reached end-of-text without balancing — no usable JSON here.
        return None
    return None


def extract_json(text: str) -> str:
    """Best-effort extraction of a JSON object from a model response.

    Handles three common cases:
      1. Pure JSON — return as-is.
      2. JSON wrapped in ```json fences.
      3. JSON embedded in prose — first **balanced** `{...}` block.
    """
    text = text.strip()
    if not text:
        raise ValueError("Empty response")
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass
    # Try fenced block first — strip the fence opener, then balance from there.
    m = _FENCE_OPEN_RE.search(text)
    if m:
        candidate = _find_balanced_json(text, start=m.end())
        if candidate:
            return candidate
    # Otherwise, search the whole text.
    candidate = _find_balanced_json(text)
    if candidate:
        return candidate
    raise ValueError(f"No JSON object found in response: {text[:120]}...")
