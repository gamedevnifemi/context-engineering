# Privacy

A Claude Code transcript is a complete record of a working session, and this public repository's
tooling runs against exactly those files. Nothing derived from a transcript may identify the
person or machine it came from, and the safeguards have to keep working after a context
compaction, when the session working in the repo has forgotten how they were set up.

## What is enforced

- **Transcripts are read in place.** They are never copied into the repository, and the
  generated `out/` directory is not tracked.
- **Identifiers are pseudonyms.** Every project and session identifier passes through
  `ctxeng.redact` before it is printed or written. An alias is a salted hash prefix; the salt is
  created on first use under `~/.ctxeng/` (or `CTXENG_HOME`) and never leaves the machine.
  `--raw` shows real identifiers for local work.
- **Content checks run on every commit and in CI.** `scripts/privacy_check.py` scans staged
  content and the commit message through the hooks in `.githooks/`, and a GitHub Actions
  workflow runs it over the whole tree on every push without printing matched text. It uses the
  same patterns `ctxeng.redact` uses to scrub output, plus a local terms file
  (`~/.ctxeng/terms.txt`, or `CTXENG_TERMS_FILE`, or the `CTXENG_TERMS` environment variable;
  one entry per line, `#` for comments). The terms file is never committed and its contents are
  never written into repository files. Adding the terms as a repository secret named
  `CTXENG_TERMS` extends the CI check; that is optional.
- **Published findings are aggregate-only.** `ctxeng report --publish` produces distributions and
  ranges, no per-session or per-event rows and no session identifiers; groups backed by fewer than
  three sessions are omitted; integration-specific tool names are collapsed to one label; charts
  label sessions by rank and model. Corpus descriptions in prose use approximate counts. The
  detailed report stays in `out/`.
- **Commits use a GitHub no-reply address**, configured for this repository only.
- **`CLAUDE.md` restates the rules** so that any session, including one that has just compacted,
  re-reads them before touching git.

## Setup on a new machine

```bash
git config core.hooksPath .githooks
mkdir -p ~/.ctxeng && printf '# one term per line\n' > ~/.ctxeng/terms.txt   # then add your own
python scripts/privacy_check.py .
```

## Limits

The checks read text. Images and other binaries are not scanned and are reviewed by eye before
they are committed. Strings that only exist at run time are invisible to the checks, which is how
the unit tests exercise the patterns without tripping them on their own source. Generation is not
review: read every table and chart before publishing it.

## When a check fails

Fix the content: use a placeholder such as `~/...` or `C:\Users\<you>\...`, an `example.com`
address, or remove the reference. Do not weaken the checks and do not bypass the hooks.
