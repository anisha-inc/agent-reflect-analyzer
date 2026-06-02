"""Top-level orchestrator for stages [3]/[4]/[5] + merge.

Called from analyzer.run.run_pipeline. Splits sessions by interestingness rank
into top-K (Opus full flatten) and rest (Haiku map-reduce); optionally runs
OpenClio-style clustering on Haiku summaries; merges all candidates by
pattern_id.
"""

from __future__ import annotations

from typing import Any

from .. import audit, identity
from . import clio, flatten, mapreduce
from .schemas import Candidate, ClusterFinding, HaikuSummary, OpusFindings


def _merge(opus: OpusFindings, clusters: list[ClusterFinding]) -> list[Candidate]:
    seen: dict[str, Candidate] = {}
    for f in opus.findings:
        c = Candidate.from_opus(f)
        seen[c.pattern_id] = c
    for cl in clusters:
        c = Candidate.from_cluster(cl)
        # Avoid hard duplicates if Opus already named the same pattern_id.
        if c.pattern_id in seen:
            seen[c.pattern_id].frequency += cl.frequency
            continue
        seen[c.pattern_id] = c
    return list(seen.values())


def _filter_min_freq(
    candidates: list[Candidate], min_opus_freq: int = 2, min_cluster_freq: int = 3
) -> list[Candidate]:
    out: list[Candidate] = []
    for c in candidates:
        threshold = min_cluster_freq if c.source == "cluster" else min_opus_freq
        if c.frequency >= threshold:
            out.append(c)
    return out


def run(
    *,
    sessions: list[dict[str, Any]],
    events_by_session: dict[str, list[dict[str, Any]]],
    top_k: int,
    model_top_k: str,
    model_rest: str,
    concurrency: int,
    cluster: bool,
    api_key_fallback: bool,
    record: audit.RunRecord,
    strategy: str,
    since: str,
) -> list[Candidate]:
    if not sessions:
        return []

    try:
        dev_id = identity.dev_id()
    except Exception:
        dev_id = "unknown"
    try:
        proj_id = identity.proj_id()
    except Exception:
        proj_id = "unknown"

    top = sessions[:top_k]
    rest = sessions[top_k:]
    record.top_k = len(top)
    record.rest_count = len(rest)

    # Strategy gating — for tests / experiments. Default "hybrid" runs all.
    if strategy in ("hybrid", "flatten-A"):
        opus_findings = flatten.analyze_top_k(
            sessions=top,
            events_by_session=events_by_session,
            dev_id=dev_id,
            proj_id=proj_id,
            since=since,
            model=model_top_k,
            record=record,
            api_key_fallback=api_key_fallback,
        )
    else:
        opus_findings = OpusFindings()

    haiku_summaries: list[HaikuSummary] = []
    if strategy in ("hybrid", "map-reduce-B", "cluster-D"):
        haiku_summaries = mapreduce.map_rest(
            rest=rest,
            events_by_session=events_by_session,
            dev_id=dev_id,
            proj_id=proj_id,
            model=model_rest,
            concurrency=concurrency,
            record=record,
        )

    clusters: list[ClusterFinding] = []
    if cluster and (strategy in ("hybrid", "cluster-D")) and haiku_summaries:
        clusters = clio.cluster_summaries(
            summaries=haiku_summaries,
            min_freq=3,
            model=model_rest,
            concurrency=concurrency,
            record=record,
        )

    merged = _merge(opus_findings, clusters)
    candidates = _filter_min_freq(merged)
    return candidates
