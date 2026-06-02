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
- **title:** Sub-2: code extraction → agent-reflect-analyzer v1.0.0
- **worktree:** local git worktree (path omitted — public repo)

## Goal

Lift the `analyzer/` package from the internal source repo into this public
repository and ship an immutable initial release `v1.0.0` — CI green on the
tag commit and a clean-shell smoke run passing.

## Roadmap

- [x] Step 1: Bootstrap worktree + verify target repo is public
- [x] Step 2: Copy analyzer package + tests + templates (promote templates into package)
- [ ] Step 3: Pydantic Settings v2 strict env loader (`AGENT_REFLECT_*`, no defaults) + cross-cutting
- [ ] Step 4: `subprocess_util.run_external()` wrapper + migrate call sites + ruff guard
- [ ] Step 5: Audit stdout fallback when `CLAUDE_PLUGIN_DATA` unset
- [ ] Step 6: scrub-test pre-commit + forbidden-patterns + source cleanup pass
- [ ] Step 7: pytest-socket + STYLE.md + renovate.json
- [ ] Step 8: Reusable workflow + vendored github-app-token + sync-drift workflow
- [ ] Step 9: Slim CI (py-tests + ruff + scrub-test + subprocess-guard)
- [ ] Step 10: Lift release workflow AS-IS
- [ ] Step 11: LICENSE (MIT) + README
- [ ] Step 12: Final verification + initial-release PR + tag `v1.0.0`

## Decisions

- Branch = the tracker's magic branch name so the PR auto-links to the issue.
- Journal is kept in-repo (commit guard requires it) but scrubbed of internal
  identifiers, since this repository is public.
- Templates promoted into the package (`analyzer/templates/`) so the wheel
  bundles them without a force-include.

## Dead Ends

## Next Action

Step 3 — rewrite `analyzer/config.py` as a pydantic-settings v2 `Settings`
class (strict, `extra="forbid"`, no defaults) and thread it through
`auth.py`, `issues.py`, `dedup.py`, `cli.py`/`run.py`, `checks.py`.

## Follow-ups
