# Roadmap

## Phase 1: diagnosis

Done:

- Transcript locator and parser with usage de-duplication, prompt classification, compaction and
  attachment extraction, subagent summaries.
- Metrics: context curve, baseline, prompt cost, window fills, composition, compaction rows,
  context drops.
- CLI with pseudonymous output, Markdown and CSV report, optional charts.
- Privacy scanner wired into git hooks, denylist outside the repo, standing rules in `CLAUDE.md`.
- First findings on a real corpus.

Next, in rough order:

1. **Post-compaction quality proxies.** Within the first N turns after a compaction, count files
   re-read that had been read before, commands re-run, tool errors, and user messages that read
   as corrections. Compare with a matched window before the compaction.
2. **Explain context drops.** Confirm that model switches account for all large drops, and
   quantify the per-model difference in token counting on identical context.
3. **Attribute growth to tools precisely.** Use per-call `cache_creation_input_tokens` as the
   exact delta and assign it to the records between consecutive calls, replacing the
   character-based composition estimate with token-accurate figures.
4. **Injected context.** Measure how often listings and edited-file notices are re-injected and
   what they cost per session.
5. **Effort experiment.** Nearly all observed sessions ran at the two highest effort levels.
   Run comparable work at lower levels to give H2 a fair test.
6. **Subagent accounting.** Compare tokens spent inside subagents with what came back into the
   main context, to see how much delegation actually saves.

## Phase 2: interventions

Each candidate is listed with the metric that would have to move for it to count as a success.

| Candidate | Mechanism | Success metric |
|---|---|---|
| Structured hand-off before compaction | A `PreCompact` hook writes a task-state file (goals, decisions, files touched, open items); a `SessionStart` hook re-injects it | Lower cost of the first turns after compaction; fewer re-reads |
| Earlier, cheaper compaction | Compact at a lower threshold, or clear tool results progressively, so summaries are written from a less crowded window | Higher retained share of useful state; no rise in prompts per fill |
| Tool-output hygiene | Trim or paginate large tool results; prefer targeted reads over whole files | Lower tool-result share in composition; more prompts per fill |
| Write-through discipline | Keep decisions and progress in files the model can re-read, rather than only in conversation | Smaller drop in quality proxies after compaction |
| Delegation policy | Push exploration and long-running work to subagents so only conclusions enter the main context | More prompts per fill at equal output |
| Slimmer fixed context | Prune instruction files and listings | Lower baseline context |
| Effort tuning | Use the highest effort only where it pays | Lower per-prompt growth at equal task outcomes |

## Phase 3: continuous measurement

Run the report on a schedule, keep dated findings, and compare each intervention's before and
after windows with the same instruments. Hooks only enter the picture here, once there is
something worth automating and a way to tell whether it helped.
