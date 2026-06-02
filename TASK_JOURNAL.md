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
- [x] Step 10: Lift release workflow AS-IS (+ bootstrap guard: idle until a tag exists)
- [x] Step 11: LICENSE (MIT) + README + version bump to 1.0.0
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
- The scrub pattern list does NOT include bare `anisha`: the org slug
  (`anisha-inc/...` in the README `uses:` line, LICENSE, settings.json) is
  unavoidably public — the repo physically lives there. Genuinely-internal
  identifiers are scrubbed by hand and enforced by the scrub-test gate.
- Post-review remediation (after maintainer feedback): renamed the company-
  prefixed op-token env var to the neutral `OP_SVC_TOKEN` (re-exported as the
  standard `OP_SERVICE_ACCOUNT_TOKEN` for `op`); generalized the emitted-issue
  template provenance. The scrub pattern list is NO LONGER committed (it would
  be a consolidated internal-name leak) — it is sourced from a private GitHub
  Actions variable `SCRUB_FORBIDDEN_PATTERNS` (provisioned via Terraform/Atlas)
  in CI, or a local gitignored `.security/forbidden-patterns.txt` for
  pre-commit; scrub-test skips with a warning when neither is present.
  Also dropped the hardcoded `anisha-inc` default for `GH_APP_TARGET_ORG` in the
  vendored token script — it is now required for discovery (the analyzer always
  passes it; direct CLI use must set it or `GH_APP_INSTALLATION_ID`).

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

- Removed the `[tool.hatch.build.targets.wheel.force-include]` table entirely:
  `analyzer/llm/prompts` is inside the package, so hatchling already bundles it
  and the force-include caused a double-include build failure (`uv build`). The
  wheel now bundles all `.j2` prompts + the issue template via default package
  data. Verified `uv build` + `unzip -l` (33 files, templates present).

- CI fix-ci #1: the 7 `test_redact` failures were presidio's `AnalyzerEngine()`
  requiring a spaCy model (absent in CI → fail-open → nothing redacted), and its
  `EmailRecognizer` fetching the public-suffix list via tldextract (blocked by
  `--disable-socket`). Fix: run pure-regex recognizers directly (no
  `AnalyzerEngine`) + a self-contained `EMAIL_ADDRESS` regex. Fully offline;
  verified all 8 `test_redact` pass under socket lockdown with presidio installed.

## Dead Ends

## Next Action

PR #1 open and **CI fully green** (ruff, scrub-test, py-tests, subprocess-guard,
status). One fix-ci iteration applied (offline redact). PR is MERGEABLE but
`REVIEW_REQUIRED` (branch protection). REMAINING (irreversible, awaiting explicit
confirmation): squash-merge → `git checkout main && git pull` →
`git tag -a v1.0.0 -m "..."` → `git push origin v1.0.0` →
`gh release create v1.0.0 --target <main sha>`. Then verify
`gh release view v1.0.0` + clean-shell `uv run --from git+...@v1.0.0
analyzer-cli --check --json` → exit 0.

## Follow-ups

- Add a `sync-vendored-scripts` workflow (weekly drift check of
  `scripts/github-app-token` vs the internal upstream) with a scrub-aware
  transform that re-applies the `GH_APP_OP_ITEM`-required adaptation, plus the
  `strip-vendor-header.py` / `refresh-vendor.py` helpers. Needs `VENDOR_SYNC_TOKEN`
  provisioned for this repo. Deferred from Step 8 (not v1.0.0-acceptance-blocking).
