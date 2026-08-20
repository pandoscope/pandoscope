---
name: pandoscope-stamp
description: Stamp the agentic-engineering scaffold into a project with the pandoscope CLI. Use when setting up a project as a Pandoscope-powered software factory, when asked to stamp or scaffold a repo with pandoscope, or on /pandoscope-stamp.
---

# Pandoscope stamp

Renders the
[agentic-engineering-template](https://github.com/pandoscope/agentic-engineering-template)
scaffold into a directory and leaves it committed and verified.

## Steps

1. **Resolve the runner.** `uvx pandoscope` where uv exists,
   `npx pandoscope` where only Node does — both run the same
   implementation. Done when `<runner> --version` prints a version.
2. **Collect answers.** Ask the principal for project name, slug,
   description, and repo owner; pass each as `-d KEY=VALUE`. Anything
   left unanswered falls to template defaults via `--defaults`. Done
   when every answer is either confirmed by the principal or defaulted
   deliberately.
3. **Stamp.**
   `<runner> stamp <directory> -d key=value ... [--defaults] [--vcs-ref <tag>]`.
   Done when the command exits 0 and
   `<directory>/.copier-answers.agentic.yml` exists.
4. **Adopt.** Initialize git if the directory has none, review the
   rendered tree, and commit it all as one
   `chore: stamp agentic-engineering-template scaffold` commit. Done
   when `git status` is clean.
5. **Verify.** Run `check.sh <directory>` from this skill's folder; fix
   whatever it names until it exits 0, then hand its printed residue to
   the principal. Done when the script exits 0.
