#!/usr/bin/env bash
# scrub-test — block internal identifiers from entering this public repo.
#
# Scans ADDED lines (diff) of the lifted source only — analyzer/, tests/,
# scripts/ — against .security/forbidden-patterns.txt (case-insensitive).
# README and .github/workflows legitimately reference the public org slug, so
# they are out of scope.
#
# Usage:
#   scrub-test.sh                 # staged changes (pre-commit default)
#   scrub-test.sh cached          # same
#   scrub-test.sh head            # last commit (HEAD~1..HEAD)
#   scrub-test.sh <base> [<head>] # explicit range (CI: base-sha HEAD)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PATTERNS_FILE="$ROOT/.security/forbidden-patterns.txt"
SCAN_PATHS=(analyzer tests scripts .github)

case "${1:-cached}" in
  cached) RANGE=(--cached) ;;
  head)   RANGE=(HEAD~1 HEAD) ;;
  *)      RANGE=("$1" "${2:-HEAD}") ;;
esac

# Build an ERE alternation from the pattern file (drop comments / blank lines).
PAT="$(grep -vE '^[[:space:]]*(#|$)' "$PATTERNS_FILE" | paste -sd '|' -)"
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
  echo "Fix or generalize these before committing (see .security/forbidden-patterns.txt)." >&2
  exit 1
fi
exit 0
