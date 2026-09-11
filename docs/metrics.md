# Metric definitions

All metrics come from `ctxeng.metrics` and are computed per session from the parsed transcript.
Token figures are the provider's own accounting; character figures are estimates.

## Context size

The number of tokens the model was given on one API call:

```
context = input_tokens + cache_read_input_tokens + cache_creation_input_tokens
```

Plotting this against call index gives the context curve: a sawtooth whose teeth are compactions.

## Baseline context

Context size on the very first call of a session. It approximates what is in the window before
any conversation: system prompt, instruction files, tool schemas, skill and agent listings.
Grouped by Claude Code version it shows how the fixed overhead has moved over time.

The first call necessarily includes the first prompt, so a session that opens with a very large
prompt (a pasted document, an automated brief) reports a high baseline. The median across
sessions is representative because most first prompts are short; the 90th percentile is reported
alongside it to make the exceptions visible.

## Prompt cost

How much the context grew while one prompt was handled. A prompt is any user-side message that
starts a turn: a typed prompt, a compaction summary, or a slash command. For the API calls that
belong to that turn:

```
added_tokens = sum over consecutive calls of max(0, context[i+1] - context[i])
             + output_tokens of the final call
```

The sum of positive steps rather than last-minus-first keeps the figure meaningful when a
compaction fires in the middle of a turn. The final call's output is added because it enters the
context but is not yet counted in any call's input.

Per prompt the toolkit also records API calls, tool calls, tool-result characters, output and
thinking tokens, wall-clock duration, and whether a compaction happened during the turn.

Aggregates (`ctxeng growth`) report the median and 90th percentile per group, over prompts that
reached the model at least once. Grouping by `kind` isolates the turns that begin from a
compaction summary, which is a direct measure of what re-orientation after compaction costs.

## Window fills and prompts per fill

```
window_fills     = compactions + context of the last call / CONTEXT_LIMIT
prompts_per_fill = user prompts / window_fills        (only when window_fills >= 0.5)
```

`CONTEXT_LIMIT` is 1,000,000 tokens, the window the observed sessions ran against. Claude Code
compacts a little before that, at about 967k tokens by default on such models, so a fill is
slightly less than the constant; the difference is small enough to ignore for this purpose.
Sessions with a different limit need the constant changed. Prompts per fill is the most intuitive
headline: how many things you can ask before the session compacts.

## Composition

An estimate of what entered the context over the whole session, by source, from character
counts (four characters per token is assumed). Sources: system prompt, instruction files,
listings, reminders, user prompts, compaction summaries, assistant text, assistant thinking, tool
call inputs, and tool results broken down by tool name.

This is a flow measure, not an occupancy measure: a tool result that was later cleared still
counts as having entered. For a session without compaction the two are the same.

## Compaction rows

Per compaction: trigger (auto or manual), context before and after, retained share, duration,
size of the summary, and how many calls and prompts followed. The retained share is the single
number that says how lossy the operation was.

## Context drops

A fall of at least 10% in context size between consecutive calls with no compaction record
between them. Two documented causes exist: Claude Code clears older tool outputs before it
summarises, and that clearing leaves no record in the transcript; and a mid-session model switch
changes how the same context is counted. In the first corpus, eight of ten such drops coincided
with a model switch and the other two are consistent with tool-output clearing. A user rewinding
to an earlier message would also show as a drop.

## Caveats

- **Token counts differ across models.** The same context measured 16% to 45% smaller on the
  call after a model switch. Compare growth rates within a model before comparing across them.
- **Confounding.** Sessions differ in task, project, and how the person worked. Per-model and
  per-effort splits are observational, not controlled.
- **Sample size.** A handful of long sessions dominate. The report prints counts next to every
  aggregate for this reason.
- **Characters are not tokens.** Composition shares are indicative; the token metrics are exact.
