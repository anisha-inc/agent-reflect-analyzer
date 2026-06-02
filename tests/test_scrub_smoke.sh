#!/usr/bin/env bash
# Smoke test for scripts/scrub-test.sh — verifies it blocks a forbidden token in
# an added line and passes a clean diff. Self-contained (throwaway git repo).
# Run manually: bash tests/test_scrub_smoke.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

git -C "$TMP" init -q
mkdir -p "$TMP/.security" "$TMP/scripts" "$TMP/analyzer"
cp "$ROOT/.security/forbidden-patterns.txt" "$TMP/.security/"
cp "$ROOT/scripts/scrub-test.sh" "$TMP/scripts/"
chmod +x "$TMP/scripts/scrub-test.sh"

# 1. Clean staged change → exit 0.
printf 'clean_value = 1\n' > "$TMP/analyzer/clean.py"
git -C "$TMP" add analyzer/clean.py
if ! (cd "$TMP" && bash scripts/scrub-test.sh cached); then
  echo "FAIL: clean diff should pass" >&2
  exit 1
fi
echo "ok: clean diff passes"

# 2. Dirty staged change → exit 1. Build the forbidden token at runtime so the
#    literal never appears in this file (which is itself scrubbed).
tok="SPD"; tok="${tok}-901"
printf '# see %s for context\n' "$tok" > "$TMP/analyzer/dirty.py"
git -C "$TMP" add analyzer/dirty.py
if (cd "$TMP" && bash scripts/scrub-test.sh cached); then
  echo "FAIL: dirty diff should be blocked" >&2
  exit 1
fi
echo "ok: dirty diff blocked"

echo "scrub smoke: PASS"
