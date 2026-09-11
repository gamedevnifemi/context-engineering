# Problem statement

## The symptom

A long Claude Code session fills its context window. When it is nearly full, Claude Code
compacts the conversation: the model writes a summary, and the session continues in a new window
that contains the summary plus a handful of recent messages. From that point on the assistant is
noticeably worse: it re-reads files it had already read, repeats work, loses decisions that were
made earlier, and needs more correction.

The window also seems to fill faster with newer models, which reason longer, try more things, and
call more tools per prompt. Higher effort settings appear to amplify this. The result is more
compactions per unit of work and more time spent in the degraded post-compaction state.

## Why it matters

Context is the assistant's working memory. Everything it knows about the task that is not in a
file it can re-read lives there. Compaction is a lossy operation applied to exactly that memory,
and it is applied at the worst possible moment: deep into a task, when the most state has
accumulated.

## Hypotheses to test

| # | Hypothesis | Evidence that would support it |
|---|---|---|
| H1 | Newer models consume more context per prompt | Higher per-prompt growth, more API calls and tool calls per prompt, fewer prompts per window fill, holding effort and task type as constant as the data allows |
| H2 | Higher effort levels consume more context per prompt | The same measures split by effort level |
| H3 | The quality drop is caused by how much compaction discards, not by the fill rate | Compactions retain a very small share; the first turns after a compaction are more expensive and involve re-reading |
| H4 | Fixed overhead (system prompt, instruction files, tool and skill listings) is a significant part of the window | Baseline context at the first call is a large fraction of the limit |
| H5 | A few sources dominate what enters the context | Composition analysis shows tool results or tool inputs far ahead of everything else |

## What counts as done for the diagnosis phase

- Every hypothesis above has a number attached to it, produced reproducibly from the transcripts.
- The dominant sources of context growth are identified and ranked.
- The cost of a compaction is quantified: what is kept, what the next turns cost, how long it takes.
- Open questions that the transcripts cannot answer are written down, with a plan to answer them.

## Out of scope for now

Interventions. Hooks that snapshot state before compaction, hand-off documents, changes to
instruction files, tool-output trimming, and delegation policies are all candidates, but building
them before the measurements exist would mean optimising blind. They are listed in the
[roadmap](roadmap.md) with the metric each one would have to move.
