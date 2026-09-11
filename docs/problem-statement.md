# Problem statement

## The problem

A long Claude Code session fills its context window. Near the limit Claude Code compacts: it
clears older tool outputs, asks the model to summarise the conversation, and continues in a
window that holds that summary, the most recent exchanges, and a small amount of material
restored from disk. From that point the assistant is noticeably worse at the task it was in the
middle of. It re-reads files it had already read, repeats work, loses decisions that were made
earlier, and its understanding of the project drifts away from where the previous window left
it. The session after a compaction does not yield the results its predecessor would have.

The working belief behind this project is that the summary alone is insufficient continuity. It
captures what the summariser judged important at one moment; everything it leaves out is gone,
and the successor rebuilds its understanding from a partial brief and branches from there.

## What Claude Code does at compaction

From the official documentation, listed in [references.md](references.md):

- Compaction fires automatically near the limit, at about 967k tokens on a one-million-token
  window unless `/autocompact` sets a lower point, or when the user runs `/compact`, optionally
  with a focus.
- Older tool outputs are cleared first; then the conversation is summarised. The documented
  intent is that requests and intent, key technical concepts, files examined or modified with
  important code snippets, errors and their fixes, and pending work survive, while detailed
  instructions from early in the conversation may not.
- Some material is restored from disk rather than from the summary: the system prompt,
  project-root CLAUDE.md and unscoped rules, auto memory, the plan written in plan mode, up to
  five recently read or edited files (as a path reference if a file is over 5,000 tokens), and
  invoked skill bodies under a cap. Context that hooks injected earlier is summarised with
  everything else.
- `SessionStart` hooks matching `compact` run after compaction and can add context.
- The same mechanism runs when a large idle session is resumed from a summary.

So the successor knows the task through the summary, the last few exchanges, five files, and
whatever lives in files that are reloaded. Anything else it needs it must rediscover.

## Hypotheses

| # | Hypothesis | What would support it |
|---|---|---|
| H1 | Compaction discards most of the working state | The retained share of the window is small and the summary is a few thousand tokens |
| H2 | The summary is insufficient for continuity: the successor re-derives state and diverges | The first turns after compaction cost more, re-read files and re-run commands already seen, draw corrections from the user, and contradict earlier decisions |
| H3 | What fills the window is mostly transient tool traffic, so the loss that matters is a small, identifiable residue: decisions, constraints, current state | Composition shows tool inputs and results dominate, and the residue can be enumerated per session |
| H4 | How fast the window fills sets how often the problem occurs, not how bad it is | Prompts per fill vary with model, effort and task; the cost of the turn after compaction does not |

H4 is context, not a benchmark. The corpus is one person's sessions, and nothing here compares
models or effort levels as products. The fill rate matters only because each fill is another
compaction.

## What counts as done for the diagnosis phase

- Every hypothesis has a number attached, produced reproducibly from transcripts.
- The loss at compaction is characterised: what the summary keeps, what the successor has to
  rediscover, and what it then does differently.
- The residue a hand-off would need to carry is described concretely enough to design one.
- Open questions that transcripts cannot answer are written down with a plan to answer them.

## Out of scope for now

Interventions. The documented levers already exist: a "Compact instructions" section in
CLAUDE.md, `/compact` with a focus, a lower `/autocompact` threshold, `/rewind` partial
summarisation, `PreCompact` and `SessionStart` (`compact`) hooks, and keeping state in files that
are reloaded. Choosing among them before measuring would be guessing. They are listed in the
[roadmap](roadmap.md) with the metric each one would have to move.
