<!--
TASK_JOURNAL.md — reset by /start-task, filled by task-lifecycle skills.
Protocol: references/task-journal-protocol.md
NOTE: this repository is public. Keep this journal free of internal
identifiers — ticket IDs, internal tracker URLs, personal paths, vault names.
-->

# Task Journal

## Task

- **linear-id:** internal — redacted (public repo)
- **url:** internal — redacted (public repo)
- **title:** token-agnostic issue emit — remove GitHub App minting (release v1.2.0)
- **worktree:** local git worktree (path omitted — public repo)

## Goal

Remove the GitHub App installation-token minting entirely. Issue dedup/emit must
use only the ambient `GH_TOKEN`/`GITHUB_TOKEN` from the environment (CI:
`github.token`; locally: the developer's `gh auth` token). This makes the
analyzer token-agnostic for every consumer and removes the internal-secret leak
(a 1Password item) from the public reusable-workflow interface. Ship `v1.2.0`.

Motivation: when issues are created with the default `GITHUB_TOKEN`, the author
is `github-actions[bot]` and GitHub's anti-recursion guard suppresses downstream
`issues` events — the paired plugins repo fixes Slack notifications via a
`workflow_run` workflow, so the App identity is no longer needed anywhere.

## Roadmap

- [x] Step 1: `auth.py` — `resolve_github_token()` reads only ambient env; delete
  `mint_github_token` + `_script_path`; keep `_op_read`/`read_oauth_token`/
  `read_anthropic_api_key` (Anthropic/OAuth via `OP_SVC_TOKEN`).
- [x] Step 2: callers (`issues.py`/`run.py`/`dedup.py`) — `resolve_github_token()`
  without `target_org`; actionable error when no token; drop unused `util` imports.
- [x] Step 3: `checks.py` — remove the `app_token` probe (7 probes now).
- [x] Step 4: reusable workflow — drop required input `gh_app_op_item` + env
  `GH_APP_OP_ITEM`. Delete vendored `scripts/github-app-token` + the wheel
  force-include (PF-25). Tests + README updated.
- [x] Step 5: verify — pytest 118 passed, ruff clean, actionlint clean.
- [ ] Step 6: open PR; after merge, tag + release `v1.2.0` in lockstep with the
  paired plugins shim re-pin (`@v1.1.4` → `@v1.2.0`).

## Decisions

- **[Release] v1.2.0 (minor), not major.** Removing the required input
  `gh_app_op_item` is formally a breaking workflow-interface change, but there
  are no external consumers (verified across the org) and the sole consumer (the
  paired plugins shim) is updated in lockstep — so no consumer actually breaks.
- **[Scope] No local-dev fallback (owner decision).** The token is read strictly
  from ambient env; locally the developer supplies their own `gh auth` token. No
  App minting path remains.
- **[Compat] `OP_SVC_TOKEN` stays required** — it backs the HMAC / Anthropic /
  OAuth 1P reads, unrelated to GitHub. Only the GitHub-App path is removed.

## Dead Ends

- **CI ruff-job ≠ local `ruff check`.** The CI job pins `ruff format --check` in
  addition to `ruff check`. Run `uvx ruff format --check analyzer tests` (pinned
  version) before pushing to avoid a red format job.

## Next Action

Open the PR; CI expected green (py-tests 118, ruff, actionlint). Coordinate the
lockstep release: merge this PR, then tag + `gh release create v1.2.0`, then the
paired plugins PR (shim/template re-pin to `@v1.2.0` + new `workflow_run` Slack
workflow) can merge.

## Follow-ups
