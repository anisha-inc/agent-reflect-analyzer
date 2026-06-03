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
- [ ] Step 4: PF-26 — `recent_ships` probe via DuckDB/HMAC path (drop gsutil)
- [ ] Step 5: PF-27 — chunk large sessions instead of dropping (fair-share)
- [ ] Step 6: version bump 1.1.0 + README docs (org-scoping, fail-closed, packaging)
- [ ] Step 7: create PR

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

## Next Action

Implementing via `/implement-task` (auto mode). Start at Step 1 (PF-15/19 org-scoped read).
Plan saved as a Linear document on the issue. ⚠️ Release-ordering: merge + release `v1.1.0`
**in lockstep** with the paired plugins (write `v=2`) PR; re-pin the plugins shim/template
to `@v1.1.0` in a separate PR.

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
