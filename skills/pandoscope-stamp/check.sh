#!/usr/bin/env bash
# Rung-1 checks for the pandoscope-stamp skill; the residue at the end
# names what still needs a human or agent judgement.
set -euo pipefail

fail() {
  printf '\n⚠️  **PANDOSCOPE-STAMP: %s**  ⚠️\n\n    %s\n    %s\n\n' "$1" "$2" "$3"
  exit 1
}

dir="${1:-.}"
answers="$dir/.copier-answers.agentic.yml"

[ -f "$answers" ] || fail "NO STAMP FOUND" \
  "$answers does not exist — the scaffold was not rendered." \
  "Run: uvx pandoscope stamp $dir"

grep -q "agentic-engineering-template" "$answers" || fail "WRONG TEMPLATE" \
  "$answers does not pin the agentic-engineering-template." \
  "Re-stamp: uvx pandoscope stamp $dir"

git -C "$dir" rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "NOT A GIT REPO" \
  "$dir is not a git repository, so the stamp cannot be committed." \
  "Run: git -C $dir init && git -C $dir add -A && git -C $dir commit"

[ -z "$(git -C "$dir" status --porcelain)" ] || fail "STAMP UNCOMMITTED" \
  "the working tree in $dir is dirty — the rendered scaffold is not fully committed." \
  "Commit it: git -C $dir add -A && git -C $dir commit -m 'chore: stamp agentic-engineering-template scaffold'"

cat <<'RESIDUE'
pandoscope-stamp residue (verify by hand):
- every template answer was a deliberate choice (defaults are choices too)
- org-level wiring the stamp cannot do: memory repos, org variables, app installs
RESIDUE
