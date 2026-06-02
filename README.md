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
    uses: anisha-inc/agent-reflect-analyzer/.github/workflows/reflect-agent-sessions-reusable.yml@v1.0.0
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

Pin to a specific tag (e.g. `@v1.0.0`). No floating `@v1` — every consumer pins
explicitly.

## CLI environment variables

| Env var | Required | Description |
|---|---|---|
| `AGENT_REFLECT_GCS_BUCKET` | yes | Full bucket URL (`gs://...`). |
| `AGENT_REFLECT_HMAC_AKID_REF` | yes | 1Password reference for the GCS HMAC access key id. |
| `AGENT_REFLECT_HMAC_SECRET_REF` | yes | 1Password reference for the GCS HMAC secret. |
| `AGENT_REFLECT_ANTHROPIC_KEY_REF` | yes | 1Password reference for the Anthropic API key. |
| `AGENT_REFLECT_OAUTH_TOKEN_REF` | yes | 1Password reference(s), comma-separated, for the `claude -p` OAuth token. |
| `AGENT_REFLECT_TARGET_ORG_DEFAULT` | no | Default org for `--repo` inference. |
| `ANISHA_OP_SVC_TOKEN` | yes | 1Password service-account token value (consumed by the `op` CLI). |
| `GH_APP_OP_ITEM` | for issue emit | 1Password item path (`Vault/Item`) for the GitHub App used to mint issue-write tokens. |

## License

MIT — see [LICENSE](LICENSE).
