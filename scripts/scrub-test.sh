#!/usr/bin/env bash
# scrub-test — block internal identifiers from entering this public repo.
#
# Scans ADDED lines (diff) of the lifted source — analyzer/, tests/, scripts/,
# .github/ — against a case-insensitive forbidden-pattern list.
#
# The pattern list itself is NOT stored in this public repo (it would be a
# consolidated leak). It is sourced, in order:
#   1. $SCRUB_FORBIDDEN_PATTERNS         — newline-separated patterns (CI passes
#                                          this from a private GitHub Actions var)
#   2. $SCRUB_FORBIDDEN_PATTERNS_FILE    — path to a local pattern file
#   3. .security/forbidden-patterns.txt  — local, gitignored (developer copy)
# If none is available the scan is skipped (a fresh public clone has no internal
# identifiers to leak anyway).
#
# Usage:
#   scrub-test.sh                 # staged changes (pre-commit default)
#   scrub-test.sh cached          # same
#   scrub-test.sh head            # last commit (HEAD~1..HEAD)
#   scrub-test.sh <base> [<head>] # explicit range (CI: base-sha HEAD)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCAN_PATHS=(analyzer tests scripts .github)

case "${1:-cached}" in
  cached) RANGE=(--cached) ;;
  head)   RANGE=(HEAD~1 HEAD) ;;
  *)      RANGE=("$1" "${2:-HEAD}") ;;
esac

# Source the raw pattern list from env or a local file (see header).
raw_patterns() {
  if [ -n "${SCRUB_FORBIDDEN_PATTERNS:-}" ]; then
    printf '%s\n' "$SCRUB_FORBIDDEN_PATTERNS"
    return 0
  fi
  local f="${SCRUB_FORBIDDEN_PATTERNS_FILE:-$ROOT/.security/forbidden-patterns.txt}"
  if [ -f "$f" ]; then
    cat "$f"
    return 0
  fi
  return 1
}

if ! RAW="$(raw_patterns)"; then
  echo "scrub-test: no pattern source (set SCRUB_FORBIDDEN_PATTERNS or provide a" \
       "local .security/forbidden-patterns.txt) — skipping scan." >&2
  exit 0
fi

# Build an ERE alternation (drop comments / blank lines).
PAT="$(printf '%s\n' "$RAW" | grep -vE '^[[:space:]]*(#|$)' | paste -sd '|' -)"
[ -z "$PAT" ] && exit 0

violations="$(
  git diff -U0 "${RANGE[@]}" -- "${SCAN_PATHS[@]}" | awk -v pat="$PAT" '
    /^\+\+\+ /  { file = substr($0, 7); next }                 # strip "+++ b/"
    /^@@/       { match($0, /\+[0-9]+/); ln = substr($0, RSTART + 1, RLENGTH - 1) + 0; next }
    /^\+/       { body = substr($0, 2)
                  if (tolower(body) ~ tolower(pat)) printf "%s:%d: %s\n", file, ln, body
                  ln++ }
  '
)"

if [ -n "$violations" ]; then
  echo "scrub-test: forbidden internal identifier(s) in added lines:" >&2
  printf '%s\n' "$violations" >&2
  echo "Fix or generalize these internal identifiers before committing." >&2
  exit 1
fi
exit 0
