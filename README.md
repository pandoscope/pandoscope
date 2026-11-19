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
puts `waybill/orders/<name>.yml` on disk.
That file names the role, the pass, the model tier, the subject and the tickets.
The subject is the issue or the pull request under work, as `owner/repo#n`.
The composer reads that file and sets the role.
For a reviewer it appends the review task to `CLAUDE.md`.
The task is the whole of `skills/original/thread-ledger/review/<pass>.md`.
The composer renders it as a Jinja template from the order and the pull request's clone.
An undefined variable is a composer error.
Before rendering,
the composer switches that clone to the review branch `claude/review-<pass>-<model_tier>-<code><n>` at the pull request head.
It renders `findings.schema.json`, beside the pass file, as the variable `findings_contract`.
A pass file that uses the variable `candidates` gets the hits of the prose check on the lines the pull request adds, or `none`.
The prose check is `skills/original/writing-prose/check.sh`.
The composer runs the check.
The reviewer never runs it.
For an implementer it appends the implementer task:
the pass file `src/pandoscope/reinset/tasks/implementer/<pass>.md.j2`,
rendered as a Jinja template from the order and the subject's clone.
A pass reads only its own file.
The pass `build` makes a first build on an issue,
with the tickets and the branch `claude/<code><n>-implement-<step>` from the order's base.
The pass `fix` makes a fix round on a pull request,
with the pull request's branch
and the open entries that it owns in the disposition files under `waybill/dispositions/`.
The composer reads the subject from the clone of its repository:
a ref `refs/pull/<n>/head` makes it a pull request.
A build on a pull request is a composer error, and so is a fix round on an issue.
The implementer profile carries the standing rules of every implementer.
Without an order the session has no role:
the composer installs nothing and renders the loud UNCONFIGURED state.
The Routine's saved prompt is one orientation sentence.
Every Routine saves the same sentence. It tells
the model that the hooks composed its role and task into `CLAUDE.md`.
Never run the composer from a model turn: the hook is the caller.

The composer installs the role's bundle.
It copies each skill that the profile names into `~/.claude/skills`.
It looks in `meta/reinset/skills/<name>` first,
then in the skills clone's `original/` and `derived/`,
then in a clone's vendored `.agents/skills/<name>`.
Each copy carries a marker file.
The next pass replaces a marked copy whole.
The composer refuses a directory without the marker.
It removes marked skills that the role no longer names.
It then renders the profile's hooks to `$REINSET_HOOKS` (default `~/.claude/reinset/hooks.json`).
The CLI captures hook registration at startup,
so the environment registers one dispatcher per event.
The dispatcher reads this file at every fire.

The composer writes the following keys to the answers file:
`detected` (harness facts),
`resolved` (harness, environment, role, principal, model; the role null without an order),
`order` (path, role, pass, model tier, subject, tickets; null without an order),
`errors`,
`installed` (the skills the role's bundle copied)
and `hooks` (the hooks rendered to `$REINSET_HOOKS`).

The composer validates the order against a strict schema
(`src/pandoscope/reinset/schemas/order.json`). The schema rejects
unknown keys. It requires `role`, `reviewer` or `implementer`.
The principal starts an orchestrator,
and a probe is started from within a session,
so neither has an order.
It requires `id` to equal the file
name. It takes `subject` as `owner/repo#n`. It takes `tickets`
as a list of the same form. It takes `checkouts` as a map from
`owner/repo` to a ref.
It requires `model_tier` on every order, in lowercase letters and digits only.
It requires `pass` on every order, in lowercase.
A reviewer's pass names its pass file.
An implementer's pass is `build` or `fix`.
An order that fits the schema must also fit its role's name pattern
(`src/pandoscope/reinset/order_name.py`):
`review-<pass>-<model_tier>-<code><n>-<step>` for a reviewer
and `implement-<pass>-<model_tier>-<code><n>-<step>` for an implementer.
`<code><n>` is the subject, with its repository's shortcode as written.
The shortcodes have one source, the waybill's `shortcodes.json`.
It maps each shortcode to its repository, in the format the thread ledger reads.
The schema `src/pandoscope/reinset/schemas/shortcodes.json` states its shape:
a shortcode is two to five lowercase letters,
a repository is `owner/repo` in lowercase,
and the map stands alone or under `repos` beside the forge and its link patterns.
A key that starts with `_`, such as `_comment`, is a comment.
Two shortcodes for one repository are an error, and so is a key written twice.
The step counts from 1, and a repeat run of a step takes a letter from `b`.
A name that disagrees with a field fails, and the error names the part.
A name that begins with `review` or `implement` needs the role of that pattern.
When the order does not validate against the schema,
the composer reports an error that names every violated field.
The session therefore never runs on a half-read order.

```sh
SESSION_ROOT=/home/user pandoscope compose
```

### `pandoscope order check FILE...`

Validate waybill order files against the schema that the composer
uses, and against the name patterns.
The shortcodes come from `shortcodes.json` beside the `orders/` folder,
and a missing shortcodes file fails every order.
So does a second shortcode map anywhere in the waybill,
such as another `shortcodes.json` or a `repo-codes.json`.
The command prints every violation with its field. It exits 1
when any file fails. Waybill's pull request checks run it. A broken
order therefore turns red before anyone fires on it.

### `pandoscope shortcodes check FILE`

Check a shortcode map alone, without an order:
the waybill's `shortcodes.json`, or a candidate under another name that is to replace it.
The command runs the schema,
and the loader's check for two shortcodes of one repository and for a key written twice.
It then runs the guard against a second map in the file's folder, with `FILE` as the one source.
It prints each failure with the file name and exits 1.

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
