# Privacy

## Threat model

A Claude Code transcript is a complete record of a working session: every prompt, every file the
model read or wrote, every command output, and the compaction summaries that restate all of it in
prose, including names, addresses, account identifiers and machine paths. This repository is
public and its tooling runs against exactly those files. The design goal is that nothing derived
from a transcript can identify the person or machine it came from, and that the safeguards keep
working after a context compaction, when the assistant working in this repo has forgotten the
conversation that set them up.

## Layers

1. **Read in place.** The toolkit never copies transcripts. `*.jsonl` and the `out/` directory are
   ignored by git and rejected by the scanner if staged anyway.
2. **Pseudonyms by default.** Every project slug and session id passes through `ctxeng.redact`
   before it is printed or written. Aliases are a salted SHA-256 prefix; the salt is created on
   first use in `~/.ctxeng/salt` (override with `CTXENG_HOME`) and never leaves the machine.
   `--raw` shows real identifiers for local work only.
3. **Scanner in git hooks.** `scripts/privacy_check.py` runs on every commit through
   `.githooks/pre-commit` (staged content) and `.githooks/commit-msg` (the message). It flags:
   - email addresses, except GitHub's no-reply relay, tooling attribution and RFC 2606 domains
   - home-directory paths on Windows, macOS and Linux, unless the username is a placeholder such
     as `<you>`
   - Claude Code project slugs that embed a username
   - common credential formats
   - forbidden paths: transcripts, `out/`, local configuration, denylist files
   - every term in the local denylist
4. **Denylist outside the repo.** Terms specific to the maintainer (names, handles, the names of
   other local projects) live in `~/.ctxeng/denylist.txt`, or the file named by
   `CTXENG_DENYLIST`. One term per line, `#` for comments, matched case-insensitively on word
   boundaries. Because the file is never committed, the terms it protects never appear in the
   repository either.
5. **Standing rules in `CLAUDE.md`.** The project instruction file restates the rules so that any
   assistant session, including one that has just compacted, re-reads them before touching git.
6. **Commit identity.** Commits use the GitHub no-reply address, set with
   `git config user.email` for this repository only.

## Setup on a new machine

```bash
git config core.hooksPath .githooks
mkdir -p ~/.ctxeng
printf '# personal terms, one per line\n' > ~/.ctxeng/denylist.txt   # then add your own
python scripts/privacy_check.py .                                    # scan the whole tree
```

## When the scanner blocks a commit

Fix the content. Replace a real path with `~/...` or `C:\Users\<you>\...`, replace an address
with an `example.com` one, or remove the reference. Do not add an exception to the scanner and do
not commit with `--no-verify`. Test code that must exercise the patterns assembles the offending
strings at runtime from fragments, so the source file stays clean.

## Publishing findings

Tables and charts under `docs/findings/` are generated with pseudonyms, but generation is not
review. Before committing a chart or table, read it: aliases, model names, version numbers and
token counts are fine; anything that reads like a path, a name or a project is not.
