#!/usr/bin/env bash
# One-time registry bootstrap for the pandoscope release workflow
# (docs/releasing.md). Neither registry has a name-reservation API — a
# name exists only once something is published — so the two registries
# need different treatment:
#
#   PyPI  needs NO upload: a *pending* trusted publisher, added in the
#         web UI for the not-yet-existing project, lets the release
#         workflow's first publish create it. This script only checks
#         the name is free and prints the exact form values.
#
#   npm   has no pending-publisher equivalent: the package must exist
#         before a trusted publisher can attach. With NPM_TOKEN set,
#         this script publishes a stub pandoscope@0.0.0 (a README
#         pointing at the repo, no bin) to mint the name, leaving the
#         real launcher versions to the OIDC workflow.
#
# Run it from anywhere inside the repo. Idempotent: taken names and an
# existing stub are reported, not errors.
set -euo pipefail

PKG=pandoscope
OWNER_REPO=pandoscope/pandoscope
WORKFLOW=release.yml
ENVIRONMENT=release

say() { printf '%s\n' "$*"; }
head_status() { curl -s -o /dev/null -w '%{http_code}' "$1"; }

say "== PyPI: $PKG =="
pypi_status=$(head_status "https://pypi.org/pypi/$PKG/json")
if [ "$pypi_status" = 404 ]; then
  say "Name is FREE. No upload needed — add a PENDING trusted publisher:"
  say "  https://pypi.org/manage/account/publishing/  (Add a new pending publisher, GitHub)"
  say "    PyPI project name : $PKG"
  say "    Owner             : ${OWNER_REPO%/*}"
  say "    Repository name   : ${OWNER_REPO#*/}"
  say "    Workflow name     : $WORKFLOW"
  say "    Environment name  : $ENVIRONMENT"
  say "  The release workflow's first publish then creates the project."
elif [ "$pypi_status" = 200 ]; then
  say "Project already exists: https://pypi.org/project/$PKG/"
  say "If its publisher is not configured yet, add it under the project's"
  say "Publishing settings with the same values as above."
else
  say "Unexpected HTTP $pypi_status from PyPI — check connectivity and re-run." >&2
  exit 1
fi

say ""
say "== npm: $PKG =="
npm_status=$(head_status "https://registry.npmjs.org/$PKG")
if [ "$npm_status" = 200 ]; then
  say "Package already exists: https://www.npmjs.com/package/$PKG"
elif [ "$npm_status" != 404 ]; then
  say "Unexpected HTTP $npm_status from the npm registry — re-run later." >&2
  exit 1
elif [ -z "${NPM_TOKEN:-}" ]; then
  say "Name is FREE, but NPM_TOKEN is not set — no stub published."
  say "Create a granular token with publish rights at"
  say "  https://www.npmjs.com/settings/~/tokens"
  say "then re-run:  NPM_TOKEN=... $0"
  exit 1
else
  say "Name is FREE — publishing the stub $PKG@0.0.0 to mint it."
  stub=$(mktemp -d)
  trap 'rm -rf "$stub"' EXIT
  cat >"$stub/package.json" <<JSON
{
  "name": "$PKG",
  "version": "0.0.0",
  "description": "Name reservation for the pandoscope launcher; real versions are published by the release workflow with OIDC provenance.",
  "license": "MIT",
  "repository": { "type": "git", "url": "git+https://github.com/$OWNER_REPO.git", "directory": "npm" },
  "homepage": "https://github.com/$OWNER_REPO#readme"
}
JSON
  cat >"$stub/README.md" <<MD
# pandoscope (stub)

This 0.0.0 release only reserves the name so a trusted publisher can
attach. Install a real version: https://github.com/$OWNER_REPO
MD
  cat >"$stub/.npmrc" <<'RC'
//registry.npmjs.org/:_authToken=${NPM_TOKEN}
RC
  (cd "$stub" && npm publish --access public)
  say "Stub published."
fi

say ""
say "Finish npm by attaching the trusted publisher:"
say "  https://www.npmjs.com/package/$PKG/access  (Trusted publisher, GitHub Actions)"
say "    Repository  : $OWNER_REPO"
say "    Workflow    : $WORKFLOW"
say "    Environment : $ENVIRONMENT"
say ""
say "Then merge PR #1 (or re-run the Release workflow) — the gate and"
say "'uv publish --check-url' make re-runs idempotent."
