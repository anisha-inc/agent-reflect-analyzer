#!/usr/bin/env bash
# Smoke test for scripts/scrub-test.sh — verifies it blocks a forbidden token in
# an added line, passes a clean diff, and skips when no pattern source exists.
# Self-contained (throwaway git repo + a made-up fixture token — no real
# internal identifiers). Run manually: bash tests/test_scrub_smoke.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

git -C "$TMP" init -q
mkdir -p "$TMP/.security" "$TMP/scripts" "$TMP/analyzer"
cp "$ROOT/scripts/scrub-test.sh" "$TMP/scripts/"
chmod +x "$TMP/scripts/scrub-test.sh"

# Made-up fixture pattern — not a real internal identifier, so this file does
# not itself trip the scan in the real repo.
FIXTURE_TOKEN="FORBIDDEN-FIXTURE-XYZ"
printf '%s\n' "$FIXTURE_TOKEN" > "$TMP/.security/forbidden-patterns.txt"

# 1. Clean staged change → exit 0.
printf 'clean_value = 1\n' > "$TMP/analyzer/clean.py"
git -C "$TMP" add analyzer/clean.py
if ! (cd "$TMP" && bash scripts/scrub-test.sh cached); then
  echo "FAIL: clean diff should pass" >&2
  exit 1
fi
echo "ok: clean diff passes"

# 2. Dirty staged change (contains the fixture token) → exit 1.
printf '# see %s for context\n' "$FIXTURE_TOKEN" > "$TMP/analyzer/dirty.py"
git -C "$TMP" add analyzer/dirty.py
if (cd "$TMP" && bash scripts/scrub-test.sh cached); then
  echo "FAIL: dirty diff should be blocked" >&2
  exit 1
fi
echo "ok: dirty diff blocked"

# 3. No pattern source → skip (exit 0) even with the dirty file still staged.
rm "$TMP/.security/forbidden-patterns.txt"
if ! (cd "$TMP" && SCRUB_FORBIDDEN_PATTERNS= bash scripts/scrub-test.sh cached); then
  echo "FAIL: missing patterns should skip (exit 0)" >&2
  exit 1
fi
echo "ok: missing patterns → skip"

echo "scrub smoke: PASS"
