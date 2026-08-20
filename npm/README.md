# pandoscope (npm launcher)

npm distribution of [pandoscope](https://github.com/pandoscope/pandoscope),
the agentic engineering instrument. This package contains no logic: its
`bin` resolves [uv](https://docs.astral.sh/uv/) (bundled as an npm
dependency, PATH as fallback) and runs the PyPI implementation pinned to
this package's own version — `npx pandoscope@X.Y.Z` and
`uvx pandoscope==X.Y.Z` execute the same code.

```sh
npx pandoscope stamp my-project
```

uv fetches a managed Python when none is installed, so Node is the only
prerequisite. See the
[project README](https://github.com/pandoscope/pandoscope#readme) for
commands and the Claude Code plugin.
