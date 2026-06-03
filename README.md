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
    uses: anisha-inc/agent-reflect-analyzer/.github/workflows/reflect-agent-sessions-reusable.yml@v1.1.0
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
      gh_app_op_item: Vault/GitHub App
```

Pin to a specific tag (e.g. `@v1.1.0`). No floating `@v1` — every consumer pins
explicitly.

> **Release ordering (v1.1.0):** the reader now scopes ingestion to the
> `v=2/org=<owner>` bucket layout (see below) and no longer reads the legacy
> un-partitioned `raw/dev=*/proj=*` data. It must be released **in lockstep**
> with the matching writer (`ship.sh` `v=2` layout) so newly shipped sessions
> land where the analyzer reads them; consumers re-pin to `@v1.1.0` together.

## CLI environment variables

| Env var | Required | Description |
|---|---|---|
| `AGENT_REFLECT_GCS_BUCKET` | yes | Full bucket URL (`gs://...`). |
| `AGENT_REFLECT_HMAC_AKID_REF` | yes | 1Password reference for the GCS HMAC access key id. |
| `AGENT_REFLECT_HMAC_SECRET_REF` | yes | 1Password reference for the GCS HMAC secret. |
| `AGENT_REFLECT_ANTHROPIC_KEY_REF` | yes | 1Password reference for the Anthropic API key. |
| `AGENT_REFLECT_OAUTH_TOKEN_REF` | yes | 1Password reference(s), comma-separated, for the `claude -p` OAuth token. |
| `AGENT_REFLECT_TARGET_ORG_DEFAULT` | no | Default org for `--repo` inference **and** the read-scope owner when `--repo` is omitted (see Tenant isolation). |
| `GH_TOKEN` / `GITHUB_TOKEN` | for issue emit (server-side) | Caller's GitHub token (e.g. `${{ github.token }}`). Preferred over minting an App token for dedup/emit, so cross-org runs use the caller repo's own identity. |
| `OP_SVC_TOKEN` | yes | 1Password service-account token value (consumed by the `op` CLI). |
| `GH_APP_OP_ITEM` | for issue emit (fallback) | 1Password item path (`Vault/Item`) for the GitHub App used to mint issue-write tokens when no ambient `GH_TOKEN`/`GITHUB_TOKEN` is present. |

## Tenant isolation

Reads are scoped to a single organization. The analyzer ingests only
`…/raw/v=2/org=<owner>/dev=*/proj=*/*.jsonl`, where `<owner>` is derived from
`--repo owner/name` (or `AGENT_REFLECT_TARGET_ORG_DEFAULT` when `--repo` is
omitted). With **neither** set, the run **fails closed** rather than reading
every organization's sessions. The owner is validated against the GitHub-org
charset before it reaches the read query.

Issue dedup/emit prefer the caller's ambient `GH_TOKEN`/`GITHUB_TOKEN` and only
mint an org-scoped GitHub App token as a fallback — so a server-side run in
another org uses that org's own `github.token` instead of an identity that
cannot see its private repos.

The vendored `scripts/github-app-token` minter is bundled into the wheel, so
issue emit works on the `uvx` path (not just source checkouts).

## License

MIT — see [LICENSE](LICENSE).
