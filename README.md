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

### `pandoscope compose`

Compose the session-time reinset from a SessionStart hook, per the
session answers spec
([skills#179](https://github.com/pandoscope/skills/issues/179)): detect
the harness facts, receive the intent reference (`REINSET_REF`, then the
`reinset:` line in the Routine's `routine-fire-payload` block of the
prompt passed via `--prompt-file`), resolve the intent file at its exact
commit, compare both sides, write the answers file at `$REINSET_ANSWERS`
(default `~/.claude/reinset/<session_id>.yml`) and render
`~/.claude/CLAUDE.md` from the role's profile. Profiles ship under
`src/pandoscope/reinset/profiles/`; a same-named file under
`meta/reinset/profiles/` in the session root replaces one whole. Without
a reference the render is the loud UNCONFIGURED state. Never run it from
a model turn: the hook is the caller.

```sh
SESSION_ROOT=/home/user pandoscope compose --prompt-file prompt.txt
```

### `pandoscope spawn --role ROLE --task-file FILE`

Spawn a worker session (the CCoW sender of
[skills#179](https://github.com/pandoscope/skills/issues/179)): mint a
spawn id, write `intents/<spawn-id>.yml` to session-memory main with the
caller's principal id as `spawner` (read from `$REINSET_ANSWERS`, never
guessed) and fire the spawn Routine named by `REINSET_SPAWN_ROUTINE`
with the `reinset:` reference line followed by the task. The fire token
comes from `REINSET_SPAWN_TOKEN` and travels only in the request header.
`--dry-run` renders the intent and touches nothing. Prints the spawn id,
the reference and the minted session URL.

```sh
pandoscope spawn --role implementer --task-file task.md \
  --thread per-session-agent-config --ticket pandoscope/skills#179
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
