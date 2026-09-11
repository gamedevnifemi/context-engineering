# First look: how context is consumed and what compaction costs

Date: 2026-09-11. Toolkit 0.1.0. Every project and session identifier below is a pseudonym.
Definitions are in [metrics.md](../metrics.md); caveats are at the end and matter.

## The corpus

- 278 main-session transcripts and 96 subagent transcripts, about 320 MB, from 23 June to
  10 September 2026, across Claude Code releases 2.1.178 to 2.1.267.
- Four models: Opus 4.8, Opus 5, Fable 5, Fable 5.1.
- Most files are tiny, one to three calls driven by automation. Fifteen sessions have at least
  five API calls and hold nearly all the volume. Ten of those filled at least half a window.
- Almost every call ran at one of the two highest effort levels.
- Eleven of twenty-four project folders had already been emptied by the default 30-day retention
  before this analysis began. Whatever those sessions would have shown is gone.

## 1. How many prompts fill the window

Sessions that filled at least half of the one-million-token window, in date order.

| date | session | model | effort | prompts | compactions | window fills | prompts per fill |
|---|---|---|---|---|---|---|---|
| 2026-06-23 | session-b7e016 | Opus 5 | xhigh | 240 | 1 | 1.7 | 142 |
| 2026-07-21 | session-46f857 | Fable 5 | max | 378 | 6 | 6.2 | 61 |
| 2026-07-26 | session-b7ac56 | Opus 5 | xhigh | 118 | 1 | 1.3 | 89 |
| 2026-08-06 | session-6a1ae1 | Fable 5 | xhigh | 129 | 1 | 1.4 | 90 |
| 2026-08-13 | session-343cff | Opus 5 | max | 76 | 1 | 1.4 | 55 |
| 2026-08-18 | session-0a3e86 | Fable 5 | max | 58 | 0 | 0.7 | 89 |
| 2026-08-18 | session-8e300c | Fable 5 | max | 83 | 0 | 0.8 | 102 |
| 2026-09-01 | session-6422bc | Fable 5.1 | max | 32 | 0 | 1.0 | 33 |
| 2026-09-03 | session-ff0b8c | Fable 5.1 | xhigh | 31 | 1 | 1.1 | 29 |
| 2026-09-03 | session-5abd4f | Fable 5.1 | max | 65 | 0 | 1.0 | 68 |

The three Fable 5.1 sessions filled the window in 29 to 68 prompts. The seven earlier sessions
took 55 to 142. This is the clearest single number behind the feeling that the window "fills
quickly now". It is also the most confounded: different projects, different weeks, different
kinds of work.

## 2. Context growth per prompt

Median and 90th percentile of tokens added to the context while one prompt was handled, over
prompts that reached the model.

| model | sessions | prompts | added, median | added, p90 | API calls, median | API calls, p90 | tool calls, median | tool result chars, median |
|---|---|---|---|---|---|---|---|---|
| Fable 5 | 10 | 714 | 5,205 | 26,334 | 3 | 8 | 2 | 775 |
| Fable 5.1 | 4 | 118 | 7,254 | 82,455 | 4 | 12 | 4.5 | 1,986 |
| Opus 4.8 | 2 | 20 | 14,095 | 50,801 | 3 | 11 | 2.5 | 1,254 |
| Opus 5 | 6 | 301 | 4,649 | 22,486 | 3 | 13 | 2 | 969 |

Fable 5.1 adds about 40% more per prompt at the median than Fable 5 and three times more at the
90th percentile. It makes roughly twice the tool calls per prompt and pulls in two and a half
times the tool-result text. The distribution is also much wider: a typical prompt is only
somewhat more expensive, but the expensive ones are far more expensive.

![Growth per prompt by model](img/2026-09-11-growth-by-model.png)

By effort level:

| effort | sessions | prompts | added, median | added, p90 | API calls, median | API calls, p90 |
|---|---|---|---|---|---|---|
| high | 3 | 52 | 5,336 | 15,969 | 2.5 | 7.9 |
| xhigh | 14 | 476 | 4,620 | 22,693 | 2 | 11 |
| max | 10 | 567 | 6,496 | 35,013 | 3 | 10 |

Maximum effort adds about 40% more per prompt than xhigh at the median and about 55% more at the
90th percentile. The `high` sample is too small to say much.

## 3. What compaction keeps

Every compaction event in the corpus.

| date | session | model | trigger | tokens before | tokens after | retained | duration | summary size |
|---|---|---|---|---|---|---|---|---|
| 2026-07-24 | session-46f857 | Fable 5 | manual | 971,443 | 15,678 | 1.6% | 3.9 min | 29.8k chars |
| 2026-08-08 | session-b7ac56 | Opus 5 | manual | 978,456 | 12,684 | 1.3% | 2.6 min | 23.8k chars |
| 2026-08-19 | session-343cff | Opus 5 | manual | 963,993 | 12,784 | 1.3% | 2.7 min | 20.0k chars |
| 2026-08-25 | session-46f857 | Opus 5 | auto | 804,863 | 110,735 | 13.8% | 4.3 min | 33.5k chars |
| 2026-08-26 | session-b7e016 | Opus 5 | manual | 976,567 | 11,134 | 1.1% | 2.4 min | 17.2k chars |
| 2026-08-26 | session-46f857 | Fable 5 | manual | 970,737 | 25,393 | 2.6% | 4.0 min | 25.0k chars |
| 2026-08-26 | session-46f857 | Fable 5 | auto | 990,393 | 87,432 | 8.8% | 5.3 min | 32.9k chars |
| 2026-08-28 | session-46f857 | Fable 5 | manual | 971,524 | 17,010 | 1.8% | 2.8 min | 27.4k chars |
| 2026-08-29 | session-46f857 | Fable 5 | auto | 1,016,623 | 27,427 | 2.7% | 2.5 min | 21.9k chars |
| 2026-09-04 | session-ff0b8c | Fable 5.1 | auto | 999,900 | 19,139 | 1.9% | 2.4 min | 21.9k chars |
| 2026-09-06 | session-6a1ae1 | Fable 5 | auto | 970,399 | 25,007 | 2.6% | 2.5 min | 20.3k chars |

- All eleven fired between 0.80M and 1.02M tokens. Nobody compacts early.
- Manual compactions kept 1.1% to 2.6% of the context. Automatic ones kept 1.9% to 13.8%; the two
  that kept more than 8% preserved a longer tail of recent messages.
- The summary itself is 17k to 34k characters, roughly 4k to 8k tokens. Everything else the new
  window holds is preserved recent messages.
- Each compaction took two and a half to five minutes of wall-clock time.

![Context over a session](img/2026-09-11-context-curves.png)

## 4. The first turn after a compaction

Turns that start from a compaction summary rather than a typed prompt, compared with ordinary
turns.

| turn starts from | turns | added, median | added, p90 | API calls, median | API calls, p90 | tool calls, median | tool result chars, median |
|---|---|---|---|---|---|---|---|
| a compaction summary | 5 | 12,347 | 32,541 | 4 | 17 | 4 | 2,537 |
| a user prompt | 1,144 | 5,252 | 28,773 | 3 | 10 | 2 | 876 |

The re-orientation turn costs about 2.3 times a normal turn at the median, with twice the tool
calls and three times the tool-result text: the model re-reading what the summary left out. Five
data points, but all in the same direction.

## 5. What fills the context

Share of characters that entered the context, by source, for the six largest sessions.

![What filled the context](img/2026-09-11-composition.png)

The three largest, top sources only (token figures are estimates from characters):

| source | session-46f857 | session-b7e016 | session-b7ac56 |
|---|---|---|---|
| tool call inputs (writes, edits, commands) | 28% | 29% | 32% |
| tool results: Read | 25% | 19% | 8% |
| assistant text | 12% | 16% | 17% |
| tool results: Bash | 12% | 9% | 10% |
| reminders and environment | 10% | 5% | 7% |
| tool, agent and skill listings | 2% | 9% | 9% |
| user prompts | 6% | 4% | 3% |
| web search and fetch results | 3% | 7% | 8% |
| compaction summaries | 2% | 1% | 1% |

- The model's own tool inputs are the largest single source in five of the six sessions. That is
  file content going out through Write and Edit, and commands going out through Bash.
- Tool results are the next largest. Which tool dominates varies: one session was 90% Read
  results.
- What the person typed is 3% to 6%. Compaction summaries are 1% to 2%.
- Injected context is not free. Listings and reminders together are 7% to 17%. The skill listing
  alone is 11k to 17.5k characters per injection and was recorded 1 to 27 times per long session.
  Notices carrying the new contents of files that changed on disk appeared 3 to 72 times per
  session at 3k to 9k characters each.

Baseline context on the first call, by model (median): Fable 5.1 23.9k tokens, Opus 4.8 26.7k,
Opus 5 36.8k, Fable 5 37.2k. Two to four percent of the window. The fixed overhead is real but it
is not what fills the window.

## 6. Context drops that are not compactions

Falls of at least 10% between consecutive calls with no compaction record, largest first.

| session | before | after | dropped | model before | model after |
|---|---|---|---|---|---|
| session-46f857 | 882,654 | 556,349 | 37% | Fable 5 | Opus 5 |
| session-343cff | 731,372 | 532,377 | 27% | Fable 5 | Opus 5 |
| session-b7e016 | 379,023 | 208,697 | 45% | Opus 4.8 | Fable 5 |
| session-b7ac56 | 649,734 | 479,683 | 26% | Opus 5 | Fable 5 |
| session-b7ac56 | 842,693 | 673,463 | 20% | Opus 5 | Opus 4.8 |
| session-b7ac56 | 759,507 | 590,985 | 22% | Opus 5 | Opus 4.8 |
| session-46f857 | 395,925 | 299,197 | 24% | Fable 5 | Fable 5 |
| session-b7e016 | 602,000 | 505,971 | 16% | Fable 5 | Opus 5 |

Seven of eight coincide with a model switch, in both directions. The same context measures 20%
to 45% smaller on the call after the switch. Two consequences: raw token counts should not be
compared across models without correction, and a model switch is, incidentally, a way to buy back
a large slice of the window. The one same-model drop is unexplained; tool-result clearing and a
rewind are the candidates.

## What this supports

| hypothesis | verdict from this corpus |
|---|---|
| H1 newer model consumes more per prompt | Supported. Higher median, much higher tail, more tool calls, a third of the prompts per fill. Confounded. |
| H2 higher effort consumes more per prompt | Supported at max versus xhigh. Lower levels untested. |
| H3 the quality drop comes from how much compaction discards | Consistent. 86% to 99% discarded; the next turn costs 2.3 times normal. Direct quality proxies not yet measured. |
| H4 fixed overhead is a large share of the window | Not supported. 2% to 4%. |
| H5 a few sources dominate growth | Supported. Tool inputs and tool results are half to nine tenths. |

## Caveats

- Ten long sessions carry the analysis, three of them on the newest model. Splits by model and
  effort are observational and confounded by project and task.
- Token counting differs by model, as section 6 shows, so cross-model token comparisons carry an
  uncertainty of the same order as some of the differences reported.
- Composition is estimated from characters and measures what entered the context, not what
  occupied it at any moment.
- Nearly every session ran at the two highest effort levels, so the effort comparison is narrow.

## Open questions

1. What does the model actually do in the turns after a compaction? Files re-read, commands
   re-run, corrections from the user. This is the direct measure of the quality drop.
2. Are re-injected listings and edited-file notices sent to the model each time they are
   recorded, and what do they cost in tokens rather than characters?
3. What caused the same-model context drop?
4. Would compacting earlier, from a less crowded window, produce a summary that retains more of
   what matters?

Next steps are in the [roadmap](../roadmap.md).
