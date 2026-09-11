# Decision log

Short records of choices that shape the project. Newest last.

## 2026-09-11: Read transcripts in place, no archive

Claude Code already keeps a complete transcript per session. Copying them into a private archive
would add a sync mechanism, a second copy of sensitive data, and machine-specific setup. The
toolkit reads the originals wherever Claude Code put them, so it runs unchanged on anyone's
machine. The trade-off is retention: Claude Code deletes idle transcripts after a configurable
period, so users who want history should raise `cleanupPeriodDays`.

## 2026-09-11: Diagnose before intervening

Hooks and other interventions are deferred until the measurements exist. Building them first
would mean optimising without a baseline to compare against.

## 2026-09-11: Public from the first commit

The repository is public. Privacy is therefore enforced by tooling (scanner, hooks, pseudonyms)
rather than by remembering to be careful, and the rules are written into `CLAUDE.md` so they
survive context compaction in assistant sessions.

## 2026-09-11: Standard library only for the core

The parser, metrics and CLI use nothing outside the Python standard library so they can run
anywhere Claude Code runs, including as a future hook. Charts are an optional extra.

## 2026-09-11: Pseudonyms are salted hashes with a local salt

Stable across runs on one machine, so findings can refer to the same session over time, and
irreversible for anyone reading a published report. Sequential aliases were rejected because
they would change whenever a transcript was deleted.

## 2026-09-11: Personal denylist lives outside the repository

A denylist inside the repo would itself publish the terms it is meant to hide. The scanner reads
it from the user's home directory or an environment variable.

## 2026-09-11: Usage is counted once per request id

Claude Code writes one assistant record per content block and repeats the usage figures on each.
The parser groups records by `requestId` and keeps a single usage entry per call, taking the
larger value per field if they ever differ.

## 2026-09-11: Prompt cost is the sum of positive context steps plus final output

Last-minus-first breaks when a compaction fires mid-turn. Summing only positive steps between
consecutive calls, then adding the last call's output, gives a figure that stays meaningful and
equals last-minus-first in the common case.

## 2026-09-11: Scripts say what they are for, not what they guard

Hook scripts and the content checker carry one-line headers that point at `docs/privacy.md`.
Enumerating what the checks protect against, or where local configuration lives, belongs in one
reviewed document rather than scattered through code that anyone can read in isolation.

## 2026-09-11: Published output is coarser than local output

Tables meant for publication show month-level dates and merge integration-specific tool names
under one label. Exact timestamps and full tool names would let a reader correlate sessions with
public activity or learn what is installed on the machine. Local CSVs keep the detail.

## 2026-09-11: Checks also run in CI

A GitHub Actions workflow runs the content checker over the whole tree on every push, without
printing matched text. Hooks are per-clone configuration and are easy to forget after a fresh
clone; the workflow is the backstop. Extra terms can be supplied as a repository secret, which is
left to the owner to decide.

## 2026-09-11: Context limit is a constant

The observed sessions ran against a one-million-token window. `CONTEXT_LIMIT` is a module
constant used only for the window-fills metric; making it a per-session inference was not worth
the complexity yet.
