# First look: what compaction costs a session

Date: 2026-09-11. Toolkit 0.1.0. Produced with `ctxeng report --publish`: aggregates and ranges
only, no per-session rows. Metric definitions are in [metrics.md](../metrics.md). Statements
about how Claude Code behaves come from the official documentation listed in
[references.md](../references.md).

This page is about one problem: what a session loses when its context is compacted, and what
the session after the compaction does about it. It is not a comparison of models. The corpus is
one person's sessions, and the model and effort figures in section 5 are there only because they
set how often compaction happens.

## The corpus

- A few hundred sessions from one Claude Code installation over about three months, June to
  September 2026, spanning Claude Code 2.1.x releases and four models.
- Most sessions are short and automated. Fifteen have at least five API calls and carry the
  analysis; ten of those filled at least half of a one-million-token window.
- Nearly every call ran at one of the two highest effort levels.
- Close to half of the project folders had already been emptied by the default 30-day retention
  before the analysis began.

## 1. The compaction event

The documentation says Claude Code compacts near the limit, about 967k tokens on a 1M window,
clears older tool outputs first, then summarises, keeping requests, key technical concepts, files
with important snippets, errors and fixes, and pending work. Eleven events in the corpus,
grouped by what triggered them:

| trigger | events | tokens before | tokens after | retained | duration | summary size |
|---|---|---|---|---|---|---|
| manual | 6 | 964k to 978k | 11k to 25k | 1.1% to 2.6% | 2.4 to 4.0 min | 17k to 30k chars |
| automatic | 5 | 805k to 1,017k | 19k to 111k | 1.9% to 13.8% | 2.4 to 5.3 min | 20k to 34k chars |

- Every event fired between 0.80M and 1.02M tokens, consistent with the documented threshold.
  Even the manual ones were run within a few tens of thousands of tokens of the limit. Nobody
  compacts early.
- Manual compactions kept 1.1% to 2.6% of the window. Automatic ones kept 1.9% to 13.8%; the two
  that kept more than 8% carried 20 and 294 recent messages over verbatim, against 4 to 27 for
  the others.
- The summary itself is 17k to 34k characters, roughly 4k to 8k tokens. Everything else in the
  new window is preserved recent messages plus what Claude Code reloads from disk.
- Each compaction took between two and a half and five and a half minutes, which matches the
  documentation's note that compacting a large context is itself a large request.

![Context over a session](img/2026-09-11-context-examples.png)

Example A is the session with the most compactions; Example B is the largest session that never
compacted. The shape is the same everywhere: near-linear growth to the limit, then a cliff.

## 2. The successor's first turn

Turns that begin from a compaction summary rather than a typed prompt, compared with ordinary
turns. This is the first direct measure of what the successor has to do to get going again.

| turn starts from | turns | added, median | added, p90 | API calls, median | API calls, p90 | tool calls, median | tool result chars, median |
|---|---|---|---|---|---|---|---|
| a compaction summary | 5 | 12,347 | 32,541 | 4 | 17 | 4 | 2,537 |
| a user prompt | 1,147 | 5,335 | 28,811 | 3 | 10 | 2 | 877 |

The re-orientation turn costs about 2.3 times a normal turn at the median, with twice the tool
calls and three times the tool-result text: the model reading back what the summary left out.
Five data points, all in the same direction. What this cannot yet show is whether the
successor's later work diverged from where the predecessor was heading; that needs the measures
in the [roadmap](../roadmap.md).

## 3. What was in the window when it was compacted

Share of characters that entered the context, by source, over the six largest sessions. The
median describes a typical session; the pooled figure weights sessions by volume and is
dominated by one very large session.

| source | typical session | pooled | range across sessions |
|---|---|---|---|
| tool call inputs (writes, edits, commands) | 30% | 17% | 5% to 42% |
| tool results: Read | 14% | 57% | 0% to 90% |
| assistant text | 12% | 7% | 1% to 17% |
| tool results: Bash | 9% | 6% | 2% to 33% |
| reminders and environment | 8% | 5% | 1% to 17% |
| tool, agent and skill listings | 7% | 3% | 0% to 11% |
| user prompts | 2% | 2% | 0% to 6% |
| tool results: WebSearch | 1% | 1% | 0% to 6% |
| tool results: Edit | 1% | 0% | 0% to 1% |
| compaction summaries | 1% | 1% | 0% to 2% |
| tool results: WebFetch | 1% | 1% | 0% to 3% |

![What filled the context](img/2026-09-11-composition.png)

The six sessions are numbered by size and labelled by model. No two are filled the same way.

What this says about the problem:

- Most of the volume is transient. Tool inputs (the model's own file writes, edits and commands)
  and tool results are half to nine tenths of everything that entered. Much of that is stale by
  the time compaction runs, and the documentation confirms tool outputs are the first thing
  cleared.
- The residue that matters for continuity is small. The person's own words are 2% of a typical
  session; the assistant's prose, where decisions get stated, is 12%. A hand-off that carried
  those two faithfully would be a fraction of the window.
- So the loss at compaction is not proportional to the 86% to 99% of tokens discarded. It is
  whatever part of that small residue the summary failed to capture. Measuring that directly is
  the next step.

## 4. What the successor gets back without the summary

The documentation lists what is restored from disk after compaction: the system prompt,
project-root CLAUDE.md and unscoped rules, auto memory, the plan written in plan mode, up to five
recently read or edited files, and invoked skills under a cap. Two observations from the data:

- Baseline context on the first call of a session, by model, has a median of about 24k to 37k
  tokens: two to four percent of the window. That is the size of the restored scaffolding. It is
  real, but it is not what fills the window, and it comes back for free.
- Injected context is not free during the session. Listings and reminders are about 15% of a
  typical long session. The listing of available skills and tools is re-injected several thousand
  tokens at a time, up to a couple of dozen times in the longest sessions, and notices carrying the
  new contents of files that changed on disk recur dozens of times at several thousand characters
  each. These are summarised away at compaction like everything else.

The baseline figure includes the first prompt, which is why its 90th percentile is far higher
for one model: a batch of short automated sessions opened with prompts of around 100k characters.

## 5. How often it happens

This section is context for the sections above, not a benchmark. Fill rate determines how many
compactions a piece of work goes through; it says nothing about the quality of any model.

Prompts per window fill, over sessions that filled at least half the window:

| model | sessions | min | median | max |
|---|---|---|---|---|
| Fable 5 | 4 | 61 | 89 | 102 |
| Fable 5.1 | 3 | 29 | 33 | 68 |
| Opus 5 | 3 | 55 | 89 | 142 |

Context added per prompt, median and 90th percentile, over prompts that reached the model:

| model | sessions | prompts | added, median | added, p90 | API calls, median | tool calls, median |
|---|---|---|---|---|---|---|
| Fable 5 | 10 | 714 | 5,205 | 26,334 | 3 | 2 |
| Fable 5.1 | 4 | 120 | 7,544 | 82,126 | 4 | 4.5 |
| Opus 5 | 6 | 302 | 4,671 | 22,476 | 3 | 2 |

| effort | sessions | prompts | added, median | added, p90 |
|---|---|---|---|---|
| high | 3 | 52 | 5,336 | 15,969 |
| xhigh | 14 | 479 | 4,670 | 22,879 |
| max | 10 | 567 | 6,496 | 35,013 |

In this corpus the newest model's sessions filled the window in roughly a third of the prompts
the others took, with more tool calls and a much heavier tail per prompt, and the highest effort
level added about 40% more per prompt than the next one down. Both are confounded by project
and task, and the documentation's own description of `max` effort as prone to overthinking is
consistent with the effort figure. The practical reading is narrow: at these settings a working
session meets compaction every few dozen prompts, so the cost measured in section 2 is paid
often.

![Growth per prompt by model](img/2026-09-11-growth-by-model.png)

## 6. Measurement notes

- Ten falls of at least 10% in context size between consecutive calls had no compaction record.
  Eight coincide with a mid-session model switch, in both directions, with the same context
  measuring 16% to 45% smaller afterwards. Token counts therefore differ by model and should not
  be compared across models without care. The other two are consistent with the documented
  clearing of older tool outputs, which is not marked in the transcript.
- Composition is estimated from characters and measures what entered the window, not what
  occupied it at any moment.
- The transcript format is documented as internal and subject to change; every figure here
  depends on the parser reading it correctly.

## What this supports

| hypothesis | verdict from this corpus |
|---|---|
| H1 compaction discards most of the working state | Supported. 86% to 99% of the window discarded; summaries of 4k to 8k tokens. |
| H2 the summary is insufficient: the successor re-derives state and diverges | Partly supported. The re-orientation turn costs 2.3 times normal with heavier reading. Divergence itself is not yet measured. |
| H3 the loss that matters is a small residue inside mostly transient traffic | Consistent. Tool traffic is half to nine tenths of the window; the person's words and the assistant's prose are about 14%. |
| H4 fill rate sets frequency, not severity | Consistent. Prompts per fill varied from 29 to 142 across sessions; the post-compaction cost is measured independently of it. |

## Caveats

- Ten long sessions carry the analysis. All splits are observational and confounded by project
  and task. Nothing here generalises beyond this corpus.
- Five post-compaction turns is a small sample for the central measurement.
- Token counting differs by model, as section 6 shows.
- Nearly every session ran at the two highest effort levels, so lower levels are unobserved.

## Open questions

1. What does each summary actually contain, compared with what was in the window? Which
   decisions, constraints and file states made it in, and which did not.
2. What does the successor re-read and re-run, where does the user correct it, and where does
   its later work contradict decisions from before the compaction?
3. Does compacting earlier, from a less crowded window, or with a focus, produce a summary that
   carries more of the residue?
4. How much do the five reloaded files and the plan-mode plan help? In other words, does keeping
   state in files change what the successor does?

Next steps are in the [roadmap](../roadmap.md).
