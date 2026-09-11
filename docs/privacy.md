# Privacy

## Why this exists

A Claude Code transcript is a complete record of a working session: every prompt, every file the
model read or wrote, every command output, and summaries that restate all of it in prose. This
repository is public and its tooling runs against exactly those files. The goal is that nothing
derived from a transcript can identify the person or machine it came from, and that the
safeguards keep working when the person, or the assistant session, working in the repo has
forgotten how they were set up.

The safeguards do not rely on secrecy. The code is public; what stays private is the data and
the local configuration.

## Layers

1. **Read in place.** Transcripts are never copied into the repository. Transcript files, the
   generated `out/` directory and local configuration are ignored by git and refused by the
   checks if staged anyway.
2. **Pseudonyms by default.** Every project and session identifier passes through
   `ctxeng.redact` before it is printed or written. An alias is a salted hash prefix. The salt is
   128 random bits created on first use, stored under `~/.ctxeng/` (or `CTXENG_HOME`), and never
   leaves the machine, so aliases are stable locally and cannot be reversed from a published
   report. `--raw` shows real identifiers for local work only.
3. **Content checks in git hooks.** `scripts/privacy_check.py` runs on every commit through the
   hooks in `.githooks/`: staged content before the commit, the message after it is written. The
   built-in checks cover contact details, home-directory paths on any operating system, Claude
   Code project folder names that embed a username, common credential formats, and file types
   that cannot be scanned. Text is normalised first so look-alike and invisible characters cannot
   hide a match.
4. **Local terms.** Anything specific to the maintainer that the built-in checks would not
   recognise is listed in a local file, `~/.ctxeng/terms.txt` (or `CTXENG_TERMS_FILE`), and can
   also be supplied through the `CTXENG_TERMS` environment variable. One entry per line, `#` for
   comments, matched case-insensitively on word boundaries. The file is never committed and its
   contents are never written into repository files, including documentation.
5. **Continuous check.** A GitHub Actions workflow runs the same checks over the whole tree on
   every push and pull request, without printing matched text. It catches a clone where the hooks
   were never enabled. Adding the local terms as a repository secret named `CTXENG_TERMS` extends
   it beyond the built-in checks; that is optional and a decision for the repository owner.
6. **Standing rules.** `CLAUDE.md` restates the rules so that any assistant session, including one
   that has just compacted, re-reads them before touching git.
7. **Commit identity.** Commits use a GitHub no-reply address, configured for this repository only.

## What published output leaves out

- Project and session identifiers: aliases only.
- Dates: month resolution in tables meant for publication. Exact timestamps stay in the local CSVs.
- Tool names from external integrations are collapsed to a single label, since they reveal what
  is installed on the machine.
- Anything that reads like a path, a name, or a project. Generation is not review: read every
  table and chart before committing it.

## Setup on a new machine

```bash
git config core.hooksPath .githooks
mkdir -p ~/.ctxeng && printf '# one term per line\n' > ~/.ctxeng/terms.txt   # then add your own
python scripts/privacy_check.py .                                            # scan the tree
```

## Limits

The checks read text as it will be committed. They cannot see inside images, which are accepted
and listed for manual review, or inside strings that only exist at run time, which is how the
unit tests exercise the patterns without tripping the checks on their own source. Formats that
cannot be read as text at all are refused. None of this replaces reading what is about to be
published.

## When a check fails

Fix the content. Replace a real path with `~/...` or `C:\Users\<you>\...`, replace an address
with an `example.com` one, or remove the reference. Do not weaken the checks and do not bypass
the hooks.
