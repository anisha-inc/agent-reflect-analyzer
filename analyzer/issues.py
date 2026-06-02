"""Render and create GitHub issues from Candidate objects.

The skill calls `--emit-issues --repo owner/name`; this module mints a token
(via auth.mint_github_token), renders `templates/issue_body.j2`, and shells out
to `gh issue create --label improvement-by-agent --body-file <tmp>`.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import tempfile
from typing import Any

import jinja2

from . import auth, config
from .llm.schemas import Candidate

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
        autoescape=False,
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
        subprocess.check_output(
            ["gh", "label", "create", config.ISSUE_LABEL,
             "--repo", repo,
             "--color", "FBCA04",
             "--description", "Pattern detected by agent-reflect analyzer (SPD-125)"],
            env=env, text=True, stderr=subprocess.STDOUT, timeout=15,
        )
    except subprocess.CalledProcessError as e:
        # `gh label create` exits non-zero if label already exists; treat as OK.
        if e.output and "already exists" in e.output:
            pass
        # Otherwise the subsequent `gh issue create --label` will also fail and
        # surface a clearer error.
    except subprocess.TimeoutExpired:
        # Network slow / gh hung — fall through. If the label genuinely doesn't
        # exist, the subsequent `gh issue create --label` will surface the
        # error; don't abort the whole emit run on a flaky label probe.
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
        token = auth.mint_github_token()

    env = {**os.environ, "GH_TOKEN": token}
    _ensure_label(repo, env)

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(body)
        tmp = pathlib.Path(f.name)

    try:
        out = subprocess.check_output(
            ["gh", "issue", "create", "--repo", repo,
             "--title", c.title,
             "--label", config.ISSUE_LABEL,
             "--body-file", str(tmp)],
            env=env, text=True, stderr=subprocess.STDOUT, timeout=30,
        ).strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"gh issue create failed: exit={e.returncode} out={(e.output or '')[:400]}"
        ) from e
    finally:
        tmp.unlink(missing_ok=True)

    return out or None


def render_for_preview(c: Candidate) -> str:
    """Public alias used by run.py for `--dry-run --json` body_preview."""
    return _render_body(c)
