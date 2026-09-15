# Context Engineering: project rules

This repository is public. These rules apply to every file, commit, and message. Re-read this
file after any context compaction and before touching git.

## Purpose

Understand what a Claude Code session loses when its context is compacted and what the session
after it does differently, then design and measure interventions that preserve continuity.
Phase 1 is diagnosis only. Hooks and other interventions come later, once the measurements say
what to change.

This is not a benchmark of models. Figures split by model or effort are context for how often
compaction happens and must be presented that way, with the single-user caveat stated.

Statements about how Claude Code behaves (compaction, what survives it, hooks, transcript
storage) come from the official documentation and are recorded in `docs/references.md` with
their source page. Do not state such behaviour from memory; check the page and add it there.

## Privacy (non-negotiable)

- Never commit anything that identifies the maintainer or their machine: names, contact details,
  usernames, local paths, account identifiers, or the names of other local projects.
- Transcripts (`*.jsonl`), the `out/` directory, and any unredacted derived data stay out of git.
  The toolkit reads transcripts in place and never copies them into this repo.
- Findings published under `docs/` come from `ctxeng report --publish` only: aggregates and
  ranges, no per-session or per-event rows, no session identifiers (pseudonymous or not), charts
  labelled by model rather than by session, approximate corpus counts in prose. The detailed
  report stays in `out/`. Review every table and chart before committing it.
- The `.githooks/` hooks run `scripts/privacy_check.py`. On a fresh clone, enable them with
  `git config core.hooksPath .githooks` before the first commit. Do not bypass or weaken them; if
  a check blocks a commit, fix the content.
- The checks' local configuration lives outside the repository. Nothing from it is ever written
  into repository files, including this one and the documentation.
- The housekeeping audit (`ctxeng audit`) describes this machine's skills, plugins and connectors.
  Its output stays under `out/` and is never quoted in docs; examples in docs are invented.
- Examples in docs and tests use invented paths, names, and identifiers.

## Commits

- Commit messages describe the change at a high level, in terms of the project's goals, for
  example "Add per-prompt context growth metric". No references to personal setup, other
  repositories, or specific sessions.
- Inline comments and script headers follow the same register: say what a thing is for, not what
  it protects against or where local configuration lives. `docs/privacy.md` is the one place that
  explains the checks.
- The commit author for this repository is the GitHub no-reply address configured locally.

## Documentation

- `README.md` is the narrative entry point. `docs/` holds the problem statement, transcript format
  notes, metric definitions, privacy policy, decision log, roadmap, and dated findings.
- Record design decisions in `docs/decisions.md` and analysis results in `docs/findings/`.
  Prefer a Mermaid diagram where a picture explains structure or flow better than prose.

## Code

- Python, standard library only for the core package, so it runs anywhere Claude Code runs.
  Charts are an optional extra.
- Run the tests (`python -m unittest` or `python -m pytest`) before committing.
