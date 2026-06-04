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
- **title:** Sub-4.2b: analyzer tenant-isolation + emit/redaction hardening
- **worktree:** local git worktree (path omitted — public repo)

## Goal

Close cross-tenant read leakage in the public analyzer (filter session
ingestion by org/proj on the read side), redact transcripts at-rest, fix
app-token packaging on the uvx path, and chunk large sessions instead of
dropping them — then ship a new semver release (`v1.0.1`+).

## Roadmap

- [x] Step 1: PF-15/19 — org-scoped `v=2` read glob + fail-closed owner resolution (charset-validated) ✓ `50ef431`
- [x] Step 2: PF-29 — prefer caller `GITHUB_TOKEN` over minted App token (dedup + emit) ✓ `aad8681`
- [x] Step 3: PF-25 — package `github-app-token` in wheel (force-include) + invoke via `bash` ✓ `2e10780`
- [x] Step 4: PF-26 — `recent_ships` probe via DuckDB/HMAC path (drop gsutil) ✓ `b0440b5`
- [x] Step 5: PF-27 — chunk large sessions instead of dropping (fair-share) ✓ `3adbe77`
- [x] Step 6: version bump 1.1.0 + README docs (org-scoping, fail-closed, packaging) ✓ `4e3e7c4` (+`uv.lock` sync)
- [x] Step 7: create PR → https://github.com/anisha-inc/agent-reflect-analyzer/pull/2
- [x] Step 8 (follow-up patch → v1.1.1): reusable workflow spawns the analyzer via `uvx --from git+…@${{ github.job_workflow_sha }}` instead of `uv run`. `uv run` resolved `analyzer-cli` from the CALLER repo's checkout (no package there) → "Failed to spawn: analyzer-cli". Surfaced by the scheduled dogfood run from the paired plugins shim (startup + load-secrets OK, failed at Run analyzer). Dropped the now-unneeded caller checkout.
- [x] Step 9 (patch → v1.1.2): `github.job_workflow_sha` resolves to an EMPTY string in this run context → `uvx --from git+…@` (empty ref) failed with "Git operation failed". Replaced with an explicit pinned `ANALYZER_REF` tag (self-consistent: reusable@vX runs analyzer@vX), kept in lockstep with the release tag. Confirmed by the dogfood run (startup + setup-uv + load-secrets OK; failed only at the empty-ref uvx).
- [x] Step 10 (patch → v1.1.3): Opus Stage [3] shells out to `claude -p`, absent on the CI runner → "executable not found", which was swallowed (subprocess_util→flatten→run→cli) into an exit-0 green run with 0 findings. Fix: (a) reusable installs the Claude CLI (`npm i -g @anthropic-ai/claude-code`; headless OAuth verified via a CI spike → $0 subscription); (b) new `ExecutableNotFoundError` makes a missing binary fatal (non-zero exit) instead of fake-green, carved out of the broad excepts in `run.py`; (c) regression tests (CLI exit≠0, flatten propagation, subprocess type). Surfaced by the scheduled dogfood run.
- [x] Step 11 (→ v1.1.4): extract the version out of the repo so it can't drift. The reusable's `ANALYZER_REF` was a hardcoded tag that lagged the release (tag bumped, self-reference not) → reusable@vX ran analyzer code@vX-1. Fix: reusable takes `analyzer_ref` as a required `workflow_call` input (`ANALYZER_REF: ${{ inputs.analyzer_ref }}`); pyproject version is dynamic via `hatch-vcs` (derived from the git tag). The release tag is now the single source of truth; callers pin both `uses: ...@<tag>` and `analyzer_ref: <tag>`. Verified locally: `uv build` (1.1.4.dev0 from git), `uv lock` (root → dynamic), frozen sync + tests 24/24, actionlint.

## Decisions

- **[Scope] Redaction descoped (owner, this task).** PF-22 (redact-at-rest) and
  PF-28 (redaction/dedup decoupling) are out of scope — owner: "пока не редактировать
  вообще". Existing emit-redaction is left exactly as-is (not expanded, not decoupled,
  not removed). At-rest redaction → infra/separate task (Follow-ups).
- **[Arch] Read side moves to `v=2/org=` and stops reading legacy `raw/dev=*/proj=*`.**
  Legacy un-partitioned data is cross-tenant-contaminated; reading it would reintroduce
  PF-15. Owner derived from `--repo` (else `AGENT_REFLECT_TARGET_ORG_DEFAULT`), no org ⇒
  fail-closed. Shared `v=2/org=<owner>` layout contract with the paired plugins (write)
  task.
- **[Security] Owner is interpolated into the DuckDB glob/SQL** → validate against the
  GitHub-org charset (`^[a-z0-9](?:[a-z0-9-]{0,38})$`) before interpolation; keep the
  `S608` ruff-ignore with an updated comment.
- **[Build] `bash`-invoke the vendored script.** `force-include` does not preserve the
  exec bit, so `mint`/`check` run `bash <github-app-token>` rather than the path directly.
- **[Release] v1.1.0 (minor)** — new behaviour, not only bugfixes.

## Dead Ends

- **CI ruff-job ≠ local `ruff check`.** First CI run was red on `ruff`: the job
  runs **two** pinned commands — `uvx ruff@0.15.15 check` AND `uvx ruff@0.15.15
  format --check`. Local `uv run ruff check` passed but `format --check` flagged
  3 edited files. Fix: `uvx ruff@0.15.15 format analyzer tests`. For future:
  always run `ruff format --check` (pinned version) before pushing.

## Next Action

All 7 steps done. **PR #2 open, CI fully green** (py-tests, ruff, subprocess-guard, scrub-test,
status — fails=0 after one ruff-format fix iteration), **0 reviewer comments**. Ready for
`/finish-task` once the lockstep release is coordinated.

⚠️ Release-ordering: merge + release `v1.1.0` **in lockstep** with the paired plugins (write
`v=2`) PR; re-pin the plugins shim/template to `@v1.1.0` in a separate PR. Post-merge: tag
`v1.1.0`, push, `gh release create`.

**Evidence (per-node, CI):** unit suite 122 passed offline; `uv build` bundles
`analyzer/scripts/github-app-token`; `analyzer-cli --check --json` shows `app_token=OK` via the
new `bash` invocation. **Feature-level acceptance STILL PENDING** — cross-org dry-run with zero
foreign candidates + uvx `--check app_token=OK` must be run against the live GCS bucket in the
dogfood environment (SPD-139 setup); not closeable from CI.

## Follow-ups

- **PF-22 redact-at-rest (deferred, owner decision).** Transcripts sit unredacted in the
  bucket; true at-rest redaction needs a write-side / infra ingestion step (the paired
  plugins task chose NOT to redact in ship.sh). Track as infra.
- **PF-28 redaction/dedup decoupling (deferred).** Emit-redaction shares a `try/except`
  with dedup in `run.py` — a dedup failure silently skips the scrub. Decouple when
  redaction work is picked up again.
- **PF-19 per-org scoped HMAC read-creds (infra).** Code side now requests a single
  `org=<owner>` prefix; true isolation needs prefix-scoped HMAC keys per org provisioned
  in infra (Terraform/Atlas) — out of this repo.
