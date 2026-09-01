# Pandoscope

Agentic engineering instrument: high-level commands that let any AI agent
run a Pandoscope-powered project as a self-improving software factory. It
stamps templates, installs skills, orchestrates build, review, and memory,
and hardens itself by turning every failure into a regression test.

## Install

Every surface delivers the same Python implementation at the same
version (see [docs/releasing.md](docs/releasing.md)):

```sh
uvx pandoscope --help   # Python (uv)
npx pandoscope --help   # Node — a launcher shim that bootstraps uv
```

Agent-native: install the repository as a Claude Code plugin to get the
`pandoscope-stamp` skill:

```text
/plugin marketplace add pandoscope/pandoscope
/plugin install pandoscope@pandoscope
```

## Commands

### `pandoscope stamp [DIRECTORY]`

Render the
[agentic-engineering-template](https://github.com/pandoscope/agentic-engineering-template)
scaffold into a project directory (wraps `copier copy`).

```sh
pandoscope stamp my-project \
  -d agentic_project_name="My Project" \
  -d agentic_repo_owner=me \
  --defaults
```

More commands land as the tool grows.

## Glossary

Ubiquitous language lives in `docs/glossary/`, one file per term. Resolve a
term and its transitive dependencies with `uvx disambiguate <term>`.

- The instrument: [Pandoscope](docs/glossary/pandoscope.md)
- The actors: [Principal](docs/glossary/principal.md),
  [Pando](docs/glossary/pando.md),
  [Pando cell](docs/glossary/pando-cell.md), [Org](docs/glossary/org.md),
  [Reinset](docs/glossary/reinset.md)
- Building blocks: [Pandoscope template](docs/glossary/pandoscope-template.md),
  [Org genome](docs/glossary/org-genome.md),
  [Template stamp](docs/glossary/template-stamp.md),
  [Agent session](docs/glossary/agent-session.md)
- Memory: [Memory repo](docs/glossary/memory-repo.md),
  [Decision-memory](docs/glossary/decision-memory.md),
  [Session-memory](docs/glossary/session-memory.md),
  [Evidence-memory](docs/glossary/evidence-memory.md),
  [Decision record](docs/glossary/decision-record.md),
  [Preference set](docs/glossary/preference-set.md),
  [Record contract](docs/glossary/record-contract.md)
- Decisions: [Grilling](docs/glossary/grilling.md)
