# Roadmap

The question throughout is continuity: what a session loses at compaction and what the session
after it does differently. Every step below serves that question.

## Phase 1: diagnosis

Done:

- Transcript locator and parser with usage de-duplication, prompt classification, compaction and
  attachment extraction, subagent summaries.
- Metrics: context curve, baseline, prompt cost, window fills, composition, compaction rows,
  context drops.
- CLI with pseudonymous output, Markdown and CSV report, optional charts, and an aggregate-only
  publish variant for anything that leaves the machine.
- Privacy scanner wired into git hooks and CI, local terms file, standing rules in `CLAUDE.md`.
- First findings on a real corpus; statements about Claude Code behaviour checked against the
  official documentation ([references.md](references.md)).

Next, in order of how directly each one answers the continuity question:

1. **Summary coverage.** For each compaction, compare the summary with the window it replaced:
   which files, decisions, constraints and open items were present before and which appear in
   the summary. The summary follows a documented structure (requests and intent, technical
   concepts, files with snippets, errors and fixes, pending work), so coverage can be scored
   section by section.
2. **Successor behaviour.** In the turns after a compaction, count files re-read that had been
   read before, commands re-run, tool errors, and user messages that read as corrections. Compare
   with a matched window before the compaction. Then look for contradiction: decisions restated
   differently, files recreated, approaches abandoned earlier being tried again.
3. **Divergence experiment.** Run the same task to compaction under two conditions, with and
   without a hand-off document, and compare what the successors do. This is the only way to
   separate the summary's effect from the task's own difficulty.
4. **Account for tool-output clearing.** The documentation says older tool outputs are cleared
   before summarising and that this is separate from compaction. Identify those events in the
   transcript so they are not mistaken for anything else.
5. **Token-accurate composition.** Use per-call cache-creation tokens as the exact delta and
   assign it to the records between consecutive calls, replacing the character-based estimate.

## Housekeeping track

Runs alongside the phases above. It does not address the post-compaction drop directly; it keeps
the always-loaded context down to what is used, so every compaction summary is written from a
less crowded window and every re-injection is cheaper.

Done:

- `ctxeng audit`: inventory of skills, plugins, agents, connectors, instruction files and hooks
  with per-session cost and usage; local report; plan of reversible actions.
- `ctxeng audit --apply` and `--undo` with settings backup and file archive.
- Weekly scheduling helper.

Next:

1. Restructure oversized skill bodies for progressive disclosure, largest first, and measure the
   on-invoke cost before and after.
2. A headless review step: hand the audit's notes and the flagged files to a read-only `claude -p`
   run that proposes edits, for approval before anything changes.
3. Track the startup baseline over time so the effect of each cleanup is visible.

## Phase 2: interventions

Every lever below already exists in Claude Code. Each is listed with the metric from phase 1 that
would have to move for it to count as a success.

| Lever | Mechanism (documented) | Success metric |
|---|---|---|
| Steer the summary | A "Compact instructions" section in project-root CLAUDE.md, or `/compact` with a focus | Higher summary coverage of decisions and open items |
| Hand-off document | A `PreCompact` hook writes task state (goal, decisions, files touched, open items) to a file; a `SessionStart` hook with the `compact` matcher prints it, and Claude Code adds that output to the compacted context | Lower cost of the first turns after compaction; fewer re-reads; fewer contradictions |
| Compact earlier | `/autocompact` with a lower token count, so the summary is written from a less crowded window | Higher coverage at equal or better prompts per fill |
| Compact part of the conversation | `/rewind` with "Summarize up to here", keeping recent work verbatim | Fewer re-reads of files touched recently |
| Keep state in files | Plan-mode plans and recently edited files are reloaded from disk after compaction, so decisions written to a plan or notes file survive | Smaller drop in successor behaviour metrics |
| Keep transient traffic out | Delegate large reads and verbose commands to subagents; filter tool output with hooks | More prompts per fill, so compaction is met less often |
| Slimmer injected context | Trim listings and reminders that recur during the session | Lower share of the window spent on machinery |

The hand-off document is the most direct test of the working belief. If a good hand-off removes
most of the post-compaction cost, the summary was the problem. If it does not, the problem lies
elsewhere, for instance in the model's difficulty resuming any task from a brief.

## Phase 3: continuous measurement

Run the report on a schedule, keep dated findings, and compare each intervention's before and
after windows with the same instruments. Automation enters only here, once there is something
worth automating and a way to tell whether it helped.
