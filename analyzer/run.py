"""Top-level pipeline orchestrator. Step 4 ships a scaffold; subsequent steps
(5: DuckDB, 6: LLM, 7: dedup/redact, 8: issues) fill in real behavior.

The skeleton must already return a well-formed summary dict so that `--dry-run`
on an empty bucket / pre-prod env yields stable output for downstream UX.
"""

from __future__ import annotations

import time
from typing import Any

from . import audit
from .subprocess_util import ExecutableNotFoundError


def run_pipeline(
    *,
    record: audit.RunRecord,
    since: str,
    limit: int,
    repo: str | None,
    read_owner: str,
    emit_issues: bool,
    top_k: int,
    strategy: str,
    model_top_k: str,
    model_rest: str,
    concurrency: int,
    cluster: bool,
    include_closed_since: str | None,
    api_key_fallback: bool,
    verbose: bool,
) -> dict[str, Any]:
    # Lazy local imports so the module is importable even without optional deps.
    try:
        from . import duckdb_query, metrics
    except ImportError:  # pragma: no cover
        duckdb_query = None
        metrics = None

    sessions: list[dict[str, Any]] = []
    events_by_session: dict[str, list[dict[str, Any]]] = {}

    if duckdb_query is not None:
        try:
            con = duckdb_query.connect()
            duck_started = time.time()
            sessions = duckdb_query.load_sessions(con, since=since, limit=limit, owner=read_owner)
            events_by_session = duckdb_query.load_events_for_sessions(
                con, [s["sessionId"] for s in sessions], owner=read_owner
            )
            record.duckdb_wall_s = round(time.time() - duck_started, 2)
            con.close()
        except Exception as e:  # pragma: no cover - real-deps path
            record.warnings.append(f"duckdb_ingest_failed: {type(e).__name__}: {e}")

    record.sessions_analyzed = len(sessions)
    record.rest_count = max(0, len(sessions) - top_k)

    candidates: list[dict[str, Any]] = []

    if sessions and metrics is not None:
        # AsyncAnthropic / Anthropic clients are constructed with an explicit
        # `api_key=…` kwarg inside the LLM stages (see mapreduce/clio/flatten),
        # so no env bootstrap is needed here — keys are pulled from 1P on demand.
        try:
            from .llm import pipeline as llm_pipeline

            candidates = llm_pipeline.run(
                sessions=sessions,
                events_by_session=events_by_session,
                top_k=top_k,
                model_top_k=model_top_k,
                model_rest=model_rest,
                concurrency=concurrency,
                cluster=cluster,
                api_key_fallback=api_key_fallback,
                record=record,
                strategy=strategy,
                since=since,
            )
        except ExecutableNotFoundError:
            raise  # missing executable = fatal env misconfig, fail loud
        except Exception as e:  # pragma: no cover - real-deps path
            record.warnings.append(f"llm_pipeline_failed: {type(e).__name__}: {e}")

    record.candidates_total = len(candidates)

    # Stage [7] dedup + redact. Dedup runs regardless of --dry-run mode — the
    # whole point of dry-run is to show what *would* be emitted, including which
    # candidates would be dropped as duplicates. Previously gated on
    # `emit_issues` which made dedup_stats meaningless for dry-run.
    if candidates and repo:
        try:
            from . import dedup, redact

            existing = dedup.fetch_open_issues(repo, include_closed_since=include_closed_since)
            kept = dedup.dedup_candidates(
                candidates, existing, include_closed_since=include_closed_since
            )
            record.candidates_after_dedup = len(kept)
            record.dropped_as_duplicate = len(candidates) - len(kept)
            kept = [redact.redact_candidate(c, record=record) for c in kept]
            record.candidates_after_redact = len(kept)
            candidates = kept
        except ExecutableNotFoundError:
            raise  # missing executable = fatal env misconfig, fail loud
        except Exception as e:  # pragma: no cover - real-deps path
            record.warnings.append(f"dedup_redact_failed: {type(e).__name__}: {e}")
            record.candidates_after_dedup = len(candidates)
            record.candidates_after_redact = len(candidates)
    else:
        record.candidates_after_dedup = len(candidates)
        record.candidates_after_redact = len(candidates)

    # Stage [8] emit issues
    from . import issues as _issues_mod

    if candidates and emit_issues and repo:
        try:
            from . import auth

            token = auth.resolve_github_token()
            if token is None:
                record.warnings.append(
                    "gh_token_unavailable: no GH_TOKEN/GITHUB_TOKEN in environment"
                )
            for c in candidates:
                url = _issues_mod.emit_issue(c, repo=repo, token=token, dry_run=False)
                if url:
                    record.issue_urls.append(url)
            record.issues_emitted = len(record.issue_urls)
        except ExecutableNotFoundError:
            raise  # missing executable = fatal env misconfig, fail loud
        except Exception as e:  # pragma: no cover - real-deps path
            record.warnings.append(f"emit_failed: {type(e).__name__}: {e}")

    # Render preview bodies for --dry-run so the skill UX can show them.
    candidate_blobs: list[dict[str, Any]] = []
    for c in candidates:
        blob = c.model_dump()
        try:
            blob["body_preview"] = _issues_mod.render_for_preview(c)
        except Exception:
            blob["body_preview"] = None
        candidate_blobs.append(blob)

    record.finalize()

    return {
        "since": since,
        "limit": limit,
        "strategy": strategy,
        "sessions_analyzed": record.sessions_analyzed,
        "candidates_total": record.candidates_total,
        "candidates_after_dedup": record.candidates_after_dedup,
        "candidates_after_redact": record.candidates_after_redact,
        "issues_emitted": record.issues_emitted,
        "issue_urls": record.issue_urls,
        "dedup_stats": {
            "before": record.candidates_total,
            "after": record.candidates_after_dedup,
            "dropped_as_duplicate": record.dropped_as_duplicate,
        },
        "total_wall_s": record.total_wall_s,
        "est_cost_usd": record.est_cost_usd,
        "warnings": record.warnings,
        "candidates": candidate_blobs,
    }
