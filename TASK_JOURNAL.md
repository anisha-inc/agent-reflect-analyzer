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
- [x] Step 7: pytest-socket + STYLE.md + renovate.json
- [x] Step 8: Reusable workflow + vendored github-app-token (sync-drift workflow → Follow-ups)
- [x] Step 9: Slim CI (py-tests + ruff + scrub-test + subprocess-guard)
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
- Vendored `scripts/github-app-token` makes `GH_APP_OP_ITEM` REQUIRED (no
  internal-vault default), so nothing environment-specific is baked into a
  public file. The reusable workflow adds a `gh_app_op_item` input to supply it.
  This means the script body no longer matches the upstream byte-for-byte, so a
  naive body-diff sync would fight the scrub — hence sync-vendored is deferred
  and needs a scrub-aware transform (see Follow-ups).

## Dead Ends

## Next Action

Step 10 — lift `.github/workflows/release.yml` from the internal source AS-IS
(generic `$GITHUB_REPOSITORY` refs); actionlint it. Then Step 11 (LICENSE +
README, bump version to 1.0.0) and Step 12 (verify + PR + tag).

## Follow-ups

- Add a `sync-vendored-scripts` workflow (weekly drift check of
  `scripts/github-app-token` vs the internal upstream) with a scrub-aware
  transform that re-applies the `GH_APP_OP_ITEM`-required adaptation, plus the
  `strip-vendor-header.py` / `refresh-vendor.py` helpers. Needs `VENDOR_SYNC_TOKEN`
  provisioned for this repo. Deferred from Step 8 (not v1.0.0-acceptance-blocking).
