"""Render and create GitHub issues from Candidate objects.

The skill calls `--emit-issues --repo owner/name`; this module mints a token
(via auth.mint_github_token), renders `templates/issue_body.j2`, and shells out
to `gh issue create --label improvement-by-agent --body-file <tmp>`.
"""

from __future__ import annotations

import os
import pathlib
import tempfile

import jinja2

from . import auth, config, util
from .llm.schemas import Candidate
from .subprocess_util import run_external

_TEMPLATE_DIR = pathlib.Path(__file__).parent / "templates"


def _render_body(c: Candidate) -> str:
    # Output is plain markdown for `gh issue create --body-file`, not HTML —
    # there is no XSS surface area. Templates live in trusted code under
    # analyzer/templates/.
    # nosemgrep: python.flask.security.xss.audit.direct-use-of-jinja2.direct-use-of-jinja2
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
        undefined=jinja2.StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,  # noqa: S701 — plain-markdown output for gh, no HTML/XSS surface
    )
    tpl = env.get_template("issue_body.j2")
    # nosemgrep: python.flask.security.xss.audit.direct-use-of-jinja2.direct-use-of-jinja2
    return tpl.render(
        symptom=c.symptom,
        severity=c.severity,
        source=c.source,
        frequency=c.frequency,
        mast_taxonomy=c.mast_taxonomy,
        proposed_fix=c.proposed_fix,
        evidence_quotes=c.evidence_quotes,
        examples=c.examples,
        title=c.title,
        pattern_id=c.pattern_id,
    )


_LABEL_ENSURED: set[str] = set()


def _ensure_label(repo: str, env: dict) -> None:
    """Idempotent: create the `improvement-by-agent` label if it doesn't exist."""
    key = f"{repo}:{config.ISSUE_LABEL}"
    if key in _LABEL_ENSURED:
        return
    try:
        run_external(
            [
                "gh",
                "label",
                "create",
                config.ISSUE_LABEL,
                "--repo",
                repo,
                "--color",
                "FBCA04",
                "--description",
                "Pattern detected by the agent-reflect analyzer",
            ],
            timeout=15,
            env=env,
        )
    except RuntimeError:
        # Non-fatal: the label may already exist, or gh hung. If it genuinely
        # doesn't exist, the subsequent `gh issue create --label` surfaces a
        # clearer error — don't abort the emit run on a flaky label probe.
        pass
    _LABEL_ENSURED.add(key)


def emit_issue(
    c: Candidate,
    *,
    repo: str,
    token: str | None = None,
    dry_run: bool = False,
) -> str | None:
    """Render + create one issue. Returns the URL or None for dry-run."""
    body = _render_body(c)
    if dry_run:
        # Round-trip for the caller — they may want to show body_preview.
        return None

    if token is None:
        token = auth.resolve_github_token(target_org=util.parse_owner(repo))
    if token is None:
        raise RuntimeError(
            "no GitHub token available — set GH_TOKEN/GITHUB_TOKEN, or "
            "OP_SVC_TOKEN + GH_APP_OP_ITEM to mint an App token (PF-29)."
        )

    env = {**os.environ, "GH_TOKEN": token}
    _ensure_label(repo, env)

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(body)
        tmp = pathlib.Path(f.name)

    try:
        out = run_external(
            [
                "gh",
                "issue",
                "create",
                "--repo",
                repo,
                "--title",
                c.title,
                "--label",
                config.ISSUE_LABEL,
                "--body-file",
                str(tmp),
            ],
            timeout=30,
            env=env,
        ).strip()
    except RuntimeError as e:
        raise RuntimeError(f"gh issue create failed: {e}") from e
    finally:
        tmp.unlink(missing_ok=True)

    return out or None


def render_for_preview(c: Candidate) -> str:
    """Public alias used by run.py for `--dry-run --json` body_preview."""
    return _render_body(c)
