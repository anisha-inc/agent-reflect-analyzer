"""Stage [5] — cross-session pattern clustering over Haiku summaries.

Per plan R2: OpenClio reference impl (Phylliida/OpenClio) is the prior art.
That package isn't on PyPI as a stable wheel — we re-implement the salient
parts using sentence-transformers + scikit-learn + a small LLM cluster-naming
loop. The result is functionally similar (semantic clusters with names) and
keeps deps light.

Default is opt-in via --cluster; for short windows (--since ≤14d) it's off.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from .. import audit
from . import flatten, prompt_loader
from .schemas import ClusterFinding, HaikuSummary


def _cluster_count(n_summaries: int) -> int:
    return max(3, min(15, n_summaries // 5))


def _embed(summaries: list[HaikuSummary]) -> Any:
    """Compute sentence embeddings using all-mpnet-base-v2."""
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")
    texts = [
        f"{s.summary} | intent:{s.user_intent_category} | "
        f"trajectory:{s.trajectory_quality} | seed:{s.actionable_pattern_seed or 'NONE'}"
        for s in summaries
    ]
    return model.encode(texts, show_progress_bar=False, convert_to_numpy=True)


def _kmeans(embeddings, k: int) -> list[int]:
    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=k, n_init=10, random_state=42)
    return km.fit_predict(embeddings).tolist()


async def _name_cluster(
    members: list[HaikuSummary], client, sem: asyncio.Semaphore, model: str
) -> dict[str, str]:
    user = "\n".join(
        f"- [{s.session_id[:8]}] {s.summary} ({s.user_intent_category}/{s.trajectory_quality})"
        for s in members[:10]
    )
    system_prompt = prompt_loader.render("cluster_naming_system.j2")
    async with sem:
        msg = await client.messages.create(
            model=flatten._resolve_model(model),
            max_tokens=400,
            system=system_prompt,
            messages=[{"role": "user", "content": user}],
        )
    raw = "\n".join(b.text for b in msg.content if hasattr(b, "text") and b.text)
    payload = prompt_loader.extract_json(raw)
    import json
    out = json.loads(payload)
    return {
        "name": out.get("name", "Unnamed cluster")[:60],
        "description": out.get("description", "")[:600],
    }


async def _name_all_async(
    grouped: list[list[HaikuSummary]], model: str, concurrency: int
) -> list[dict[str, str]]:
    from anthropic import AsyncAnthropic
    from .. import auth as _auth
    api_key = _auth.read_anthropic_api_key()
    # Explicit api_key — see mapreduce._map_rest_async for rationale.
    client = AsyncAnthropic(api_key=api_key) if api_key else AsyncAnthropic()
    sem = asyncio.Semaphore(max(1, concurrency))
    tasks = [asyncio.create_task(_name_cluster(g, client, sem, model)) for g in grouped]
    return await asyncio.gather(*tasks)


def cluster_summaries(
    *,
    summaries: list[HaikuSummary],
    min_freq: int,
    model: str,
    concurrency: int,
    record: audit.RunRecord,
) -> list[ClusterFinding]:
    if len(summaries) < min_freq * 2:
        return []

    started = time.time()
    try:
        embeddings = _embed(summaries)
    except Exception as e:
        record.warnings.append(f"embed_failed: {type(e).__name__}: {str(e)[:120]}")
        record.cluster_wall_s = round(time.time() - started, 2)
        return []

    k = _cluster_count(len(summaries))
    try:
        labels = _kmeans(embeddings, k)
    except Exception as e:
        record.warnings.append(f"kmeans_failed: {type(e).__name__}: {str(e)[:120]}")
        record.cluster_wall_s = round(time.time() - started, 2)
        return []

    grouped: list[list[HaikuSummary]] = [[] for _ in range(k)]
    for s, lab in zip(summaries, labels):
        grouped[lab].append(s)
    grouped = [g for g in grouped if len(g) >= min_freq]

    if not grouped:
        record.cluster_wall_s = round(time.time() - started, 2)
        return []

    try:
        names = asyncio.run(_name_all_async(grouped, model=model, concurrency=concurrency))
    except Exception as e:
        record.warnings.append(f"cluster_name_failed: {type(e).__name__}: {str(e)[:120]}")
        names = [{"name": f"cluster-{i}", "description": ""} for i in range(len(grouped))]

    findings = [
        ClusterFinding(
            name=name["name"],
            description=name["description"],
            frequency=len(g),
            session_ids=[s.session_id for s in g],
        )
        for g, name in zip(grouped, names)
    ]
    record.cluster_count = len(findings)
    record.cluster_wall_s = round(time.time() - started, 2)
    return findings
