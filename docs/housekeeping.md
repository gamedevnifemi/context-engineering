# Housekeeping

Everything a Claude Code installation loads at session start costs tokens then, and again after
every compaction, when the listings are re-sent. Skills nobody invokes, plugins nobody uses,
connectors nobody calls, and custom agents nobody delegates to all pay that cost for nothing.
Housekeeping keeps the always-loaded set down to what is actually used.

This is hygiene, not a fix for the post-compaction quality drop. The fixed overhead is a few
percent of the window. The payoff is a cleaner window for the summariser to work from, cheaper
re-injection after each compaction, and fewer surprises such as a skill whose body is tens of
thousands of tokens entering context on every invocation.

## What Claude Code already provides

Interactive commands cover most of this on their own (see [references](references.md)):

- `/skill-doctor` reports each skill's context cost and invocation count and flags skills never
  invoked.
- `/doctor` finds unused skills, MCP servers and plugins against their cost, flags slow hooks,
  proposes CLAUDE.md trims, and asks before changing anything.
- `/plugin` lists plugins not used recently; `claude plugin details <id>` prints a plugin's
  projected always-on and on-invoke token cost.
- `claude mcp list` shows connection health for every server and connector.
- Plugins from the official marketplace update themselves in the background.

None of these run unattended, and each looks at one kind of thing. `ctxeng audit` exists to run
on a schedule and to put cost and usage for every kind side by side.

## What the audit reads

| Source | What it contributes |
|---|---|
| Configuration directory | Skills, agents, instruction files, rules, settings (hooks, overrides, denied servers, retention) |
| Plugin command line | Installed plugins, versions, enabled state, install paths, projected always-on token cost |
| MCP command line | Connection health per server and connector |
| Claude Code's state file | Its own usage counters for skills, plugins and tools, which outlive transcript retention |
| Session transcripts | The listings actually sent to the model and their sizes, tool calls per skill, agent and server, slash commands typed, hook timings |

## What it produces

All under `out/audit/`, which is not tracked and must never be quoted in published documents,
because it names the machine's skills, plugins and connectors.

- `report.md`: startup cost by source, one table per kind, notes, and the proposed actions.
- `inventory.json`: everything the report was built from.
- `plan.json`: the reversible actions the audit proposes. Edit it before applying if you disagree
  with a line.

## Rules

Usage is judged over a window, 90 days by default. "Used" means at least one invocation in the
transcripts inside the window, or a last-used date inside the window in Claude Code's counters.

| Condition | Result |
|---|---|
| Skill listed to the model, not used in the window, no override set | Action: `skillOverrides` to `user-invocable-only`. The description leaves every session; `/name` still works |
| Same, but the skill belongs to a plugin | No individual action; plugin skills are not covered by `skillOverrides` |
| Plugin enabled, none of its skills used, no plugin usage recorded, no language server | Action: disable the plugin |
| Plugin enabled, some skills used | Note listing the unused ones |
| Plugin providing a language server | Note only; its use is not visible in transcripts |
| Custom agent never delegated to in the window | Action: move the agent file to the archive |
| Server or connector loaded every session, no tool call in the window | Action: add to `deniedMcpServers` |
| Server not connected | Note with its health text |
| Skill body over 20,000 characters | Note: restructure into a short instruction file plus files read on demand |
| Instruction file over 200 lines | Note |
| Hook costing over a second per session | Note |
| Retention not set | Note that transcripts are deleted after 30 days by default |

Skills already hidden with `disable-model-invocation` or an override are not judged; they cost
nothing at startup.

## Apply and undo

`ctxeng audit --apply out/audit/plan.json` performs only the actions in the plan:

- `skill_override` and `deny_mcp` edit the user settings file. The previous file is saved first.
- `plugin_disable` runs the plugin command line tool, which is reversible with `enable`.
- `archive_file` moves the file, never deletes it.

Every run writes an undo record under `~/.ctxeng/housekeeping/<timestamp>/` (or under
`CTXENG_HOME`), containing the settings backup and the archived files.
`ctxeng audit --undo <that folder>/applied.json` restores the settings file, moves files back,
and re-enables plugins.

## Schedule

`python scripts/schedule_audit.py` registers a weekly Windows Task Scheduler entry that runs the
audit and refreshes `out/audit/`; on other systems it prints the crontab line. `--remove`
deletes the task. The audit itself never applies anything; applying is a separate, deliberate
step after reading the report.

## Measuring the effect

Before and after applying a plan, `ctxeng baseline --by model` shows the context on the first
call of new sessions. `ctxeng composition <session>` on a later long session shows the share of
listings and reminders. Both should fall.

## Limits

- Usage is visible only through transcripts and Claude Code's counters. A skill used in a way
  neither records, for example by reading its file directly, looks unused.
- Bundled skills appear only through the listing the transcripts record, so their body size is
  unknown.
- The audit does not judge content. Whether a skill's instructions are stale, or a CLAUDE.md line
  is still true, needs a reader. A later phase may hand those to a headless session that proposes
  edits for approval.
