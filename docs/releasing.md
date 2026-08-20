# Releasing

A release is a version bump merged to `main`. The `Release` workflow
(`.github/workflows/release.yml`) then publishes automatically:

1. **version gate** — reads `project.version` from `pyproject.toml`,
   re-verifies that `npm/package.json`, `.claude-plugin/plugin.json`,
   and `src/pandoscope/__init__.py` carry the same version (the
   lockstep test guards this on every PR), and skips everything when
   the tag `v<version>` already exists.
2. **publish to PyPI** — `uv build && uv publish` via PyPI trusted
   publishing.
3. **publish to npm** — `npm publish` from `npm/` via npm trusted
   publishing (OIDC provenance), after PyPI so the version the
   launcher pins exists the moment npm serves it.
4. **tag + GitHub release** — `gh release create v<version>`.

## One-time registry configuration (principal)

Both registries authenticate the workflow itself via OIDC — no
long-lived tokens in repository secrets. `scripts/register-packages.sh`
walks the whole setup: it checks both names, prints the exact
trusted-publisher form values, and (with `NPM_TOKEN` set) publishes the
npm name-reservation stub. The underlying facts:

- **PyPI**: needs no upload — add a *pending* trusted publisher at
  <https://pypi.org/manage/account/publishing/> for the
  not-yet-existing project: name `pandoscope`, owner `pandoscope`, repository
  `pandoscope`, workflow `release.yml`, environment `release`. The
  release workflow's first publish then creates the project.
- **npm**: has no pending-publisher equivalent — the package must
  exist before a trusted publisher can attach, so the script mints the
  name with a stub `pandoscope@0.0.0` (README only, no bin). Then
  attach the publisher: package `pandoscope` → Settings → Trusted
  publisher → GitHub Actions: repository `pandoscope/pandoscope`,
  workflow `release.yml`, environment `release`.

Until both are configured, the publish jobs fail with an
authentication error. Configure, then re-run the workflow — the gate
and `uv publish --check-url` make re-runs idempotent.

## Distribution surfaces

| Surface | Artifact | Source |
| --- | --- | --- |
| PyPI (`uvx pandoscope`) | wheel + sdist | `src/pandoscope` |
| npm (`npx pandoscope`) | launcher shim | `npm/` |
| Claude Code plugin | `pandoscope-stamp` skill | `skills/`, `.claude-plugin/` |

The npm launcher contains no logic: it runs
`uv tool run --from pandoscope==<its own version>`, so both ecosystems
execute the same implementation at the same version. The plugin is
installed from the repository itself
(`/plugin marketplace add pandoscope/pandoscope`), so it follows `main`
rather than the registries.
