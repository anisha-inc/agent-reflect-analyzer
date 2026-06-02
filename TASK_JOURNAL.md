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
- [x] Step 3: Pydantic Settings v2 strict env loader (`AGENT_REFLECT_*`, no defaults) + cross-cutting
- [x] Step 4: `subprocess_util.run_external()` wrapper + migrate call sites + ruff guard
- [x] Step 5: Audit stdout fallback when `CLAUDE_PLUGIN_DATA` unset
- [x] Step 6: scrub-test pre-commit + forbidden-patterns + source cleanup pass
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
- `Settings` uses `NoDecode` + a before-validator to CSV-split the OAuth refs
  from the singular `AGENT_REFLECT_OAUTH_TOKEN_REF` env var; an empty string
  raises (verified in an isolated env). `extra="forbid"` does NOT reject
  unknown prefixed env vars in this pydantic-settings version — so no test
  asserts that.
- `auth.read_*` thread `Settings` lazily (default arg), leaving the four
  `llm/` call sites untouched; load failures degrade to None.
- The automated scrub pattern list will NOT include bare `anisha`: the public
  org slug (`anisha-inc/...` in the README `uses:` line) and the kept env var
  `ANISHA_OP_SVC_TOKEN` both legitimately contain it. Genuinely-internal
  identifiers are scrubbed by hand as files are touched and by the Step 6 list.

- `run_external` gained `check=False` (returns the CompletedProcess) and `cwd`
  beyond the plan's signature, so `llm/flatten` can keep inspecting `claude -p`
  exit/stderr for quota detection without a bare `subprocess` import.
- Ran `ruff format` once over `analyzer/`+`tests/` to establish the formatting
  baseline and resolve `E501` in lifted code; `tests/**` ignores all `S` rules
  (fixtures carry dummy tokens/temp paths/subprocess mocks).

- scrub-test scans the diff of `analyzer/ tests/ scripts/ .github/` only (not the
  pattern file or root docs); reports `file:line`. The smoke test builds its
  forbidden fixture token at runtime so the literal never lands in a scanned
  file. Source verified clean of all 7 patterns.

## Dead Ends

## Next Action

Step 7 — dev deps (`pytest-socket` etc.) + pytest `addopts = "--disable-socket
--allow-unix-socket"`, `STYLE.md`, `renovate.json`; `uv lock`; verify the light
test subset still passes under socket lockdown.

## Follow-ups
