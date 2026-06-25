# agent-reflect-analyzer

Reads shipped Claude Code session transcripts from a GCS bucket, runs hybrid
LLM analysis (Opus full-flatten on the top-K most interesting sessions + Haiku
map-reduce on the rest), detects recurring failure patterns, and emits GitHub
improvement issues.

Internal tool. Public so the reusable GitHub Actions workflow can be consumed
across organizations.

## Usage as a reusable workflow

```yaml
jobs:
  reflect:
    uses: anisha-inc/agent-reflect-analyzer/.github/workflows/reflect-agent-sessions-reusable.yml@v1.3.0
    secrets:
      OP_SERVICE_ACCOUNT_TOKEN_CI: ${{ secrets.OP_SERVICE_ACCOUNT_TOKEN_CI }}
    with:
      repo: ${{ github.repository }}
      gcs_bucket: gs://your-bucket
      hmac_akid_ref: op://Vault/hmac/access_key_id
      hmac_secret_ref: op://Vault/hmac/secret_access_key
      anthropic_key_ref: op://Vault/anthropic/ANTHROPIC_API_KEY
      oauth_token_ref: op://Vault/anthropic/CLAUDE_CODE_OAUTH_TOKEN
      op_svc_token_vault_ref: op://Vault/service-account/token
```

The caller still passes 1Password `op://` references; the reusable workflow
resolves them to plain values via `load-secrets-action` and hands the analyzer
only resolved env vars (the analyzer itself never calls `op`).

Pin to a specific tag (e.g. `@v1.3.0`). No floating `@v1` — every consumer pins
explicitly.

> **Release ordering (v1.3.0):** the analyzer is now a pure env-consumer — it
> reads resolved secret **values** (`AGENT_REFLECT_HMAC_AKID/_SECRET`,
> `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`) and no longer calls `op`.
> The writer (`ship.sh`) consumes the matching contract; re-pin together.
> (Read scoping to the `v=2/org=<owner>` layout — see Tenant isolation — landed
> in v1.1.0 and is unchanged here.)

## CLI environment variables

The analyzer reads **already-resolved values** from the environment — it never
calls `op`. Resolving 1Password references into these vars happens outside: the
reusable workflow does it via `load-secrets-action`; locally a credential-sync
step / direnv populates them.

| Env var | Required | Description |
|---|---|---|
| `AGENT_REFLECT_GCS_BUCKET` | yes | Full bucket URL (`gs://...`). |
| `AGENT_REFLECT_HMAC_AKID` | yes | Resolved GCS HMAC access key id (a value). |
| `AGENT_REFLECT_HMAC_SECRET` | yes | Resolved GCS HMAC secret (a value). |
| `ANTHROPIC_API_KEY` | for Haiku stages | Anthropic API key (a value). |
| `CLAUDE_CODE_OAUTH_TOKEN` | for Opus stage | Claude Code subscription OAuth token for `claude -p` (a value). |
| `AGENT_REFLECT_TARGET_ORG_DEFAULT` | no | Default org for `--repo` inference **and** the read-scope owner when `--repo` is omitted (see Tenant isolation). |
| `GH_TOKEN` / `GITHUB_TOKEN` | for issue emit | Caller's GitHub token (e.g. `${{ github.token }}`) used for dedup/emit — issues are authored by whoever owns the token. |

## Tenant isolation

Reads are scoped to a single organization. The analyzer ingests only
`…/raw/v=2/org=<owner>/dev=*/proj=*/*.jsonl`, where `<owner>` is derived from
`--repo owner/name` (or `AGENT_REFLECT_TARGET_ORG_DEFAULT` when `--repo` is
omitted). With **neither** set, the run **fails closed** rather than reading
every organization's sessions. The owner is validated against the GitHub-org
charset before it reaches the read query.

Issue dedup/emit use the caller's ambient `GH_TOKEN`/`GITHUB_TOKEN` — so a
server-side run in another org uses that org's own `github.token`, which can see
its private repos. No App minting; issues are authored by whoever owns the token.

## License

MIT — see [LICENSE](LICENSE).
