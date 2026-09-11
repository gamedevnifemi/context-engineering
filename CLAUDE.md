# Context Engineering: project rules

This repository is public. These rules apply to every file, commit, and message. Re-read this
file after any context compaction and before touching git.

## Purpose

Diagnose how Claude Code sessions consume their context window and what compaction costs, then
design and measure interventions. Phase 1 is diagnosis only. Hooks and other interventions come
later, once the measurements say what to change.

## Privacy (non-negotiable)

- Never commit anything that identifies the maintainer or their machine: names, contact details,
  usernames, local paths, account identifiers, or the names of other local projects.
- Transcripts (`*.jsonl`), the `out/` directory, and any unredacted derived data stay out of git.
  The toolkit reads transcripts in place and never copies them into this repo.
- Anything published under `docs/` uses the pseudonyms produced by `ctxeng.redact`, month-level
  dates, and generic labels for integration-specific tool names. Review every table and chart
  before committing it.
- The `.githooks/` hooks run `scripts/privacy_check.py`. On a fresh clone, enable them with
  `git config core.hooksPath .githooks` before the first commit. Do not bypass or weaken them; if
  a check blocks a commit, fix the content.
- The checks' local configuration lives outside the repository. Nothing from it is ever written
  into repository files, including this one and the documentation.
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
