# Context Engineering: project rules

This repository is public. These rules apply to every file, commit, and message. Re-read this
file after any context compaction and before touching git.

## Purpose

Diagnose how Claude Code sessions consume their context window and what compaction costs, then
design and measure interventions. Phase 1 is diagnosis only. Hooks and other interventions come
later, once the measurements say what to change.

## Privacy (non-negotiable)

- Never commit anything that identifies the maintainer or their machine: real names, email
  addresses, OS usernames, home-directory paths, account or entry IDs, or the names of other local
  projects and repositories.
- Raw transcripts (`*.jsonl`), the `out/` directory, and any unredacted derived data stay out of
  git. The toolkit reads transcripts in place from Claude Code's own directory and never copies
  them into this repo.
- Anything published under `docs/` uses the pseudonymous project and session identifiers produced
  by `ctxeng.redact`. Review every table and chart before committing it.
- The `.githooks/` pre-commit and commit-msg hooks run `scripts/privacy_check.py`. Do not bypass
  them. If the check blocks a commit, fix the content, not the check.
- Personal terms the scanner should catch live in a denylist file outside the repository (see
  `docs/privacy.md`). Never write such terms into files inside the repo, including this one.
- Examples in docs and tests use invented paths, names, and identifiers.

## Commits

- Commit messages describe the change at a high level, in terms of the project's goals, for
  example "Add per-prompt context growth metric". No references to personal setup, other
  repositories, or specific sessions.
- Inline comments follow the same register: explain intent, never personal circumstances.
- The commit author for this repository is the GitHub no-reply address configured locally.

## Documentation

- `README.md` is the narrative entry point. `docs/` holds the problem statement, transcript format
  notes, metric definitions, privacy policy, decision log, roadmap, and dated findings.
- Record design decisions in `docs/decisions.md` and analysis results in `docs/findings/`.
  Prefer a Mermaid diagram where a picture explains structure or flow better than prose.

## Code

- Python, standard library only for the core package, so it runs anywhere Claude Code runs.
  Charts are an optional extra.
- Run the tests (`python -m pytest` or `python -m unittest`) before committing.
