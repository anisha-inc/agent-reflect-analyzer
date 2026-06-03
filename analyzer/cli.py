"""Click entry-point for analyzer-cli.

Wired flags so this can be the single entry from the skill `/reflect-agent-sessions`.
Full pipeline is invoked in `run()` below; --check is a short-circuit probe path.
"""

from __future__ import annotations

import json
import re
import sys

import click
from pydantic import ValidationError

from . import audit, checks, config, util

# GitHub org/user login charset: alphanumeric + single hyphens, 1-39 chars, no
# leading hyphen. The resolved owner is interpolated into the DuckDB read glob,
# so it must be validated to this charset before it reaches the SQL string.
_OWNER_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38})$")


def _resolve_read_owner(repo: str | None) -> str:
    """Resolve the single org the bucket read is scoped to (tenant isolation).

    Owner = ``parse_owner(--repo)`` when ``--repo owner/name`` is given, else
    ``AGENT_REFLECT_TARGET_ORG_DEFAULT``. Neither present ⇒ fail closed (refuse
    to read every org's sessions, PF-15). The result is lowercased and charset-
    validated before it is interpolated into the read glob (PF-19 / injection).
    """
    if repo and "/" in repo:
        owner = util.parse_owner(repo).lower()
    else:
        try:
            owner = (config.load_settings().target_org_default or "").strip().lower()
        except ValidationError:
            owner = ""
    if not owner:
        raise click.UsageError(
            "read scope requires an org: pass --repo owner/name "
            "(or set AGENT_REFLECT_TARGET_ORG_DEFAULT). "
            "Refusing to read all orgs — tenant isolation (PF-15)."
        )
    if not _OWNER_RE.match(owner):
        raise click.UsageError(f"invalid org owner {owner!r} for bucket read scope.")
    return owner


def _resolve_repo(repo: str | None, *, emit_issues: bool) -> str | None:
    """Resolve the issue target repo: ``--repo`` wins, else expand a bare name
    via ``AGENT_REFLECT_TARGET_ORG_DEFAULT``. Fail actionably when emitting
    without a resolvable ``owner/name``."""
    if repo and "/" in repo:
        return repo
    if not emit_issues:
        return repo
    default_org = None
    try:
        default_org = config.load_settings().target_org_default
    except ValidationError:
        default_org = None
    if repo and default_org:
        return f"{default_org}/{repo}"
    raise click.UsageError(
        "--emit-issues requires a target repository: pass --repo owner/name "
        "(or --repo name together with AGENT_REFLECT_TARGET_ORG_DEFAULT)."
    )


def _emit_check(results: list[checks.CheckResult], as_json: bool) -> int:
    if as_json:
        sys.stdout.write(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
        return 0
    checks.print_human(results)
    return 0 if checks.all_ok(results) else 1


@click.command()
@click.option("--check", "check_mode", is_flag=True, help="Run prerequisite probes and exit.")
@click.option(
    "--since",
    default=config.DEFAULT_SINCE,
    show_default=True,
    help="Window for session selection, e.g. 7d, 14d, 30d.",
)
@click.option(
    "--limit",
    type=int,
    default=config.DEFAULT_LIMIT,
    show_default=True,
    help="Hard cap on session count after ranking.",
)
@click.option(
    "--repo",
    default=None,
    help="owner/name for issue emit. If --emit-issues without --repo, autodetect via gh.",
)
@click.option(
    "--emit-issues/--dry-run",
    default=False,
    help="Default --dry-run. With --emit-issues actually open GitHub issues.",
)
@click.option(
    "--top-k",
    type=int,
    default=config.DEFAULT_TOP_K,
    show_default=True,
    help="Number of sessions taken full-flatten for Opus stage [3].",
)
@click.option(
    "--strategy",
    type=click.Choice(["hybrid", "flatten-A", "map-reduce-B", "cluster-D"]),
    default="hybrid",
    show_default=True,
    help="Pipeline strategy. hybrid = Opus top-K + Haiku map-reduce (+optional clustering).",
)
@click.option(
    "--model-top-k",
    type=click.Choice(["opus", "sonnet"]),
    default="opus",
    show_default=True,
    help="Model for stage [3].",
)
@click.option(
    "--model-rest",
    type=click.Choice(["haiku", "sonnet"]),
    default="haiku",
    show_default=True,
    help="Model for stage [4]/[5].",
)
@click.option(
    "--concurrency",
    type=int,
    default=config.DEFAULT_CONCURRENCY,
    show_default=True,
    help="Max concurrent API calls in Stage [4]/[5].",
)
@click.option(
    "--cluster/--no-cluster",
    default=False,
    show_default=True,
    help="Enable OpenClio clustering stage [5]. Off by default for --since ≤14d.",
)
@click.option(
    "--include-closed-since",
    default=None,
    help="Include closed improvement-by-agent issues from N days ago in dedup corpus.",
)
@click.option(
    "--api-key-fallback/--no-api-key-fallback",
    default=False,
    show_default=True,
    help="If `claude -p` Opus call hits subscription quota, retry with ANTHROPIC_API_KEY.",
)
@click.option("--json", "json_out", is_flag=True, help="Emit final summary as JSON to stdout.")
@click.option("--verbose", is_flag=True, help="Verbose stage logging.")
def main(
    check_mode: bool,
    since: str,
    limit: int,
    repo: str | None,
    emit_issues: bool,
    top_k: int,
    strategy: str,
    model_top_k: str,
    model_rest: str,
    concurrency: int,
    cluster: bool,
    include_closed_since: str | None,
    api_key_fallback: bool,
    json_out: bool,
    verbose: bool,
) -> None:
    """agent-reflect-analyzer — reflect Claude Code sessions, emit improvement issues."""
    if check_mode:
        results = checks.run_all()
        sys.exit(_emit_check(results, json_out))

    repo = _resolve_repo(repo, emit_issues=emit_issues)
    # Tenant-isolation: scope the bucket read to one org. Fails closed when no
    # org is resolvable (no --repo and no AGENT_REFLECT_TARGET_ORG_DEFAULT).
    read_owner = _resolve_read_owner(repo)

    # Full pipeline (Steps 5-8) lives in analyzer.run.run_pipeline. Import lazily
    # so that --check (the hot path called by skill on every invocation) doesn't
    # eagerly load DuckDB / anthropic / presidio.
    from .run import run_pipeline  # noqa: WPS433

    record = audit.RunRecord(
        since=since,
        limit=limit,
        top_k=top_k,
        strategy=strategy,
    )
    summary = run_pipeline(
        record=record,
        since=since,
        limit=limit,
        repo=repo,
        read_owner=read_owner,
        emit_issues=emit_issues,
        top_k=top_k,
        strategy=strategy,
        model_top_k=model_top_k,
        model_rest=model_rest,
        concurrency=concurrency,
        cluster=cluster,
        include_closed_since=include_closed_since,
        api_key_fallback=api_key_fallback,
        verbose=verbose,
    )
    audit_log = audit.write_audit(record)
    summary["audit_log"] = str(audit_log) if audit_log is not None else "stdout"

    if json_out:
        sys.stdout.write(json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n")
    else:
        sys.stdout.write(_summary_table(summary))
    sys.exit(0)


def _summary_table(summary: dict) -> str:
    rows = [
        ("sessions analyzed", summary.get("sessions_analyzed", 0)),
        ("candidates total", summary.get("candidates_total", 0)),
        ("after dedup", summary.get("candidates_after_dedup", 0)),
        ("after redact", summary.get("candidates_after_redact", 0)),
        ("issues emitted", summary.get("issues_emitted", 0)),
        ("wall-clock (s)", summary.get("total_wall_s", 0)),
        ("est cost (USD)", summary.get("est_cost_usd", 0)),
    ]
    lines = ["analyzer-cli summary"]
    for k, v in rows:
        lines.append(f"  {k:24s} {v}")
    if summary.get("issue_urls"):
        lines.append("\nemitted issues:")
        for u in summary["issue_urls"]:
            lines.append(f"  - {u}")
    if summary.get("audit_log"):
        lines.append(f"\naudit log: {summary['audit_log']}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
