"""Single-file audit log written under ${CLAUDE_PLUGIN_DATA}/audit/.

A single analyzer run produces one JSON record summarising probe results,
ingestion counts, LLM stage timings + tokens, dedup/redact metrics, and emitted
issue URLs. Used both for human Troubleshooting and for skill UX (`/reflect`
prints a table from the latest audit file).
"""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import sys
import time
from typing import Any

from . import config


@dataclasses.dataclass
class RunRecord:
    started_at: float = dataclasses.field(default_factory=time.time)
    since: str = ""
    limit: int = 0
    top_k: int = 0
    strategy: str = ""
    sessions_analyzed: int = 0
    rest_count: int = 0

    duckdb_wall_s: float = 0.0
    opus_input_tok: int = 0
    opus_output_tok: int = 0
    opus_wall_s: float = 0.0
    haiku_summaries_completed: int = 0
    haiku_summaries_failed: int = 0
    haiku_wall_s: float = 0.0
    cluster_count: int = 0
    cluster_wall_s: float = 0.0

    candidates_total: int = 0
    candidates_after_dedup: int = 0
    candidates_after_redact: int = 0
    dropped_as_duplicate: int = 0
    redacted: dict[str, int] = dataclasses.field(default_factory=dict)

    issues_emitted: int = 0
    issue_urls: list[str] = dataclasses.field(default_factory=list)

    est_cost_usd: float = 0.0
    total_wall_s: float = 0.0

    checks: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    warnings: list[str] = dataclasses.field(default_factory=list)

    def finalize(self) -> None:
        self.total_wall_s = round(time.time() - self.started_at, 2)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def write_audit(record: RunRecord) -> pathlib.Path | None:
    """Persist the record and return where it went.

    With ``CLAUDE_PLUGIN_DATA`` set, write a timestamped log file under the
    audit dir and return its path. Otherwise (e.g. a reusable CI workflow with
    no writable state dir) dump the record to stdout and return ``None``.
    """
    if not os.environ.get("CLAUDE_PLUGIN_DATA"):
        json.dump(record.to_dict(), sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return None
    config.AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    log = config.AUDIT_DIR / f"reflect-{int(record.started_at)}.log"
    log.write_text(json.dumps(record.to_dict(), indent=2, ensure_ascii=False))
    return log
