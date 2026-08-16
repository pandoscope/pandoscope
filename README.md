# Pandoscope

Agentic engineering instrument: high-level commands that let any AI agent
run a Pandoscope-powered project as a self-improving software factory. It
stamps templates, installs skills, orchestrates build, review, and memory,
and hardens itself by turning every failure into a regression test.

## Install

```sh
uvx pandoscope --help
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
