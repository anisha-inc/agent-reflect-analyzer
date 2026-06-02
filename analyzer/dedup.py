"""SemHash-based candidate dedup against open `improvement-by-agent` GitHub issues.

Existing issues are fetched via `gh issue list` (uses GH_TOKEN from auth.mint
helper or ambient gh auth). SemHash uses sentence-transformers embeddings +
nearest-neighbour search to detect candidates that are semantically close to
already-open patterns.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any

from . import config
from .llm.schemas import Candidate

_SYMPTOM_RE = re.compile(r"## Симптом\s+(.+?)(?=\n##|\Z)", re.S)
_FIX_RE = re.compile(r"## Fix\s+(.+?)(?=\n##|\Z)", re.S)


def parse_issue_sections(body: str) -> dict[str, str]:
    sym = _SYMPTOM_RE.search(body or "")
    fix = _FIX_RE.search(body or "")
    return {
        "symptom": (sym.group(1).strip() if sym else "")[:1000],
        "fix": (fix.group(1).strip() if fix else "")[:1000],
    }


def fetch_open_issues(repo: str, token: str | None = None,
                      include_closed_since: str | None = None) -> list[dict[str, Any]]:
    """Return a list of {number,title,body,state} dicts for label=improvement-by-agent.

    Closed issues from N days ago are appended when `include_closed_since` is
    set (e.g. "30d") so that recently-resolved patterns aren't re-emitted.

    When no token is supplied, mint one scoped to the repo owner; on failure
    fall back to the ambient `gh` auth in the environment.
    """
    if token is None:
        from . import auth, util
        try:
            token = auth.mint_github_token(target_org=util.parse_owner(repo))
        except RuntimeError:
            token = None  # fall back to ambient gh auth

    env = {**os.environ}
    if token:
        env["GH_TOKEN"] = token

    def _run(state: str, since_arg: list[str] = ()) -> list[dict[str, Any]]:
        out = subprocess.check_output(
            ["gh", "issue", "list", "--repo", repo,
             "--label", config.ISSUE_LABEL,
             "--state", state, "--limit", "200",
             "--json", "number,title,body,state,closedAt", *since_arg],
            env=env, text=True, timeout=30,
        )
        return json.loads(out or "[]")

    issues = _run("open")
    if include_closed_since:
        # gh issue list doesn't support --since; filter client-side.
        from datetime import datetime, timedelta, timezone
        days = int(re.match(r"(\d+)", include_closed_since).group(1))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        for it in _run("closed"):
            closed_at = it.get("closedAt")
            if closed_at:
                try:
                    when = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
                    if when >= cutoff:
                        issues.append(it)
                except ValueError:
                    pass
    return issues


def _candidate_text(c: Candidate) -> str:
    return f"{c.title}. {c.symptom}"


def _issue_text(it: dict[str, Any]) -> str:
    sec = parse_issue_sections(it.get("body", "") or "")
    return f"{it.get('title','')}. {sec['symptom']}"


def _fallback_dedup(
    candidates: list[Candidate], existing: list[dict[str, Any]]
) -> list[Candidate]:
    """Substring-based fallback when sentence-transformers isn't available.

    Drops a candidate if its title (lower, normalized) is wholly contained in
    any existing issue title, OR if any pattern_id token appears in the title.
    """
    existing_titles = [it.get("title", "").lower() for it in existing]

    def _matches(c: Candidate) -> bool:
        ctitle = c.title.lower()
        for et in existing_titles:
            if ctitle and ctitle in et:
                return True
            if c.pattern_id and c.pattern_id.lower() in et:
                return True
            # Split title into tokens; if 2+ tokens overlap, treat as duplicate.
            ctokens = {t for t in ctitle.split() if len(t) > 3}
            etokens = {t for t in et.split() if len(t) > 3}
            if len(ctokens & etokens) >= 2:
                return True
        return False

    return [c for c in candidates if not _matches(c)]


def dedup_candidates(
    candidates: list[Candidate],
    existing: list[dict[str, Any]],
    *,
    include_closed_since: str | None = None,
    similarity_threshold: float = 0.65,
    force_fallback: bool = False,
) -> list[Candidate]:
    """Filter candidates that semantically match any existing issue.

    Uses sentence-transformers (all-mpnet-base-v2) for embedding + cosine
    similarity. Falls back to substring matching if the embedding model
    can't be loaded (deps missing / CI lane), or when `force_fallback=True`
    (used by unit tests that want deterministic behavior without loading the
    ~420 MB model).
    """
    if not candidates:
        return []
    if not existing:
        return candidates

    if force_fallback:
        return _fallback_dedup(candidates, existing)

    try:
        from sentence_transformers import SentenceTransformer, util
        import numpy as np  # noqa: F401
    except ImportError:
        return _fallback_dedup(candidates, existing)

    try:
        model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")
        cand_texts = [_candidate_text(c) for c in candidates]
        existing_texts = [_issue_text(it) for it in existing]
        cand_emb = model.encode(cand_texts, convert_to_tensor=True, show_progress_bar=False)
        existing_emb = model.encode(existing_texts, convert_to_tensor=True, show_progress_bar=False)
        sim = util.cos_sim(cand_emb, existing_emb)
    except Exception:
        # Network or disk issue loading the model — degrade to fallback.
        return _fallback_dedup(candidates, existing)

    kept: list[Candidate] = []
    for i, c in enumerate(candidates):
        max_sim = float(sim[i].max())
        if max_sim < similarity_threshold:
            kept.append(c)
    return kept
