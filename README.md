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

Compose the session-time reinset from a SessionStart hook
([skills#179](https://github.com/pandoscope/skills/issues/179),
[skills#195](https://github.com/pandoscope/skills/issues/195),
[waybill#1](https://github.com/pandoscope/waybill/issues/1)). The
composer detects the harness facts. It reads the waybill order. It
writes the answers file at `$REINSET_ANSWERS` (default
`~/.claude/reinset/<session_id>.yml`). It renders `~/.claude/CLAUDE.md`
from the role's profile. The package ships profiles under
`src/pandoscope/reinset/profiles/`. The composer prefers a same-named
file under `meta/reinset/profiles/` in the session root; that file
replaces the shipped one whole.

The order is the only receiver. The Routine fires when a pull request
opens on the waybill repository from a branch `order/<name>`. The
harness sets `CCR_TRIGGER_REPO` and `CCR_TRIGGER_HEAD_REF` in the
environment. It also checks out the pull request head. The checkout
puts `waybill/orders/<name>.yml` on disk. That file names the role,
the pull request under work, the tickets, and for a reviewer the pass
and model tier. The composer reads that file and sets the role. For a
reviewer it appends the review task to
`CLAUDE.md`.
The task is the whole of `skills/original/thread-ledger/review/<pass>.md`.
The composer renders it as a Jinja template from the order and the pull request's clone.
An undefined variable is a composer error.
Without an order the composer sets the role general and
renders the loud UNCONFIGURED state. The Routine's saved prompt is one
orientation sentence. Every Routine saves the same sentence. It tells
the model that the hooks composed its role and task into `CLAUDE.md`.
Never run the composer from a model turn: the hook is the caller.

The composer writes four keys to the answers file: `detected`
(harness facts), `resolved` (harness, environment, role, principal,
model), `order` (path, role, pass, model tier, pull request number, tickets;
null without an order) and `errors`.

The composer validates the order against a strict schema
(`src/pandoscope/reinset/schemas/order.json`). The schema rejects
unknown keys. It requires `role`. It requires `id` to equal the file
name. It takes `pull_request` as `owner/repo#n`. It takes `tickets`
as a list of the same form. It takes `checkouts` as a map from
`owner/repo` to a ref. For a reviewer it also requires `pass` and
`model-tier`, both lowercase. When the order is off the schema, the
composer reports an error that names every violated field. The
session therefore never runs on a half-read order.

```sh
SESSION_ROOT=/home/user pandoscope compose
```

### `pandoscope order check FILE...`

Validate waybill order files against the schema that the composer
uses. The command prints every violation with its field. It exits 1
when any file fails. Waybill's pull request checks run it. A broken
order therefore turns red before anyone fires on it.

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
