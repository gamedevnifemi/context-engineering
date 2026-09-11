# Transcript format

What Claude Code writes to disk, as far as this project relies on it. Field names were observed
in transcripts from Claude Code 2.1.x releases; anything not listed here is ignored by the parser.

The documentation states that the entry format is internal to Claude Code and changes between
versions, and that scripts parsing the files directly can break on any release. This project
parses them anyway because the per-call token usage and the compaction metadata exist nowhere
else. The parser tolerates unknown record types and missing fields, and every finding names the
release range it was produced from. The sanctioned alternatives, `/export` for a rendered
transcript and the `transcript_path` field that `SessionEnd` hooks receive, do not carry the
per-call figures this analysis needs.

## Where transcripts live

```
<config>/projects/<project-slug>/<session-id>.jsonl          main session
<config>/projects/<project-slug>/<session-id>/subagents/*.jsonl   subagent transcripts
<config>/projects/<project-slug>/<session-id>/workflows/...       workflow scripts and agents
```

`<config>` is `~/.claude` unless the `CLAUDE_CONFIG_DIR` environment variable is set. The
project slug is the working directory with separators replaced by dashes, so it embeds the
username on most machines. That is why `ctxeng` never prints a slug without aliasing it.

Claude Code deletes transcripts that have not been touched for a configurable number of days
(`cleanupPeriodDays` in `settings.json`, 30 by default). Anyone who wants history for analysis
should raise that before it is gone.

## Record types

Each line is one JSON object with a `type`. The ones that matter:

| type | What it is | Fields the parser uses |
|---|---|---|
| `user` | A prompt, a tool result, or the summary that opens a post-compaction window | `message.content`, `isMeta`, `isCompactSummary`, `timestamp` |
| `assistant` | One content block of a model response | `requestId`, `message.model`, `message.usage`, `message.content`, `message.stop_reason`, `effort`, `version` |
| `system` | Control records | `subtype`, `compactMetadata` when `subtype == "compact_boundary"` |
| `attachment` | Context injected by Claude Code itself | `attachment.type`, `rendered` |

Other types seen and ignored: `mode`, `permission-mode`, `ai-title`, `last-prompt`,
`queue-operation`, `file-history-snapshot`, and a few internal latches.

Every conversational record also carries `uuid`, `parentUuid`, `sessionId`, `cwd`, `gitBranch`,
`isSidechain` (true inside subagent transcripts) and `version` (the Claude Code release).

## Token usage

`message.usage` on an assistant record is the provider's accounting for that API call:

```
input_tokens                  uncached prompt tokens
cache_read_input_tokens       prompt tokens served from cache
cache_creation_input_tokens   prompt tokens written to cache on this call
output_tokens                 generated tokens
output_tokens_details.thinking_tokens
```

The sum of the three input figures is the size of the context on that call. That sum is the
primary quantity this project tracks.

**One response, many records.** A response with a thinking block, a text block and a tool call is
written as three assistant records with the same `requestId` and identical usage. Summing usage
across records triples the numbers. The parser groups by `requestId` and counts once.

Assistant records whose model is `<synthetic>` are local notices (errors, interruptions), not
model output. Their usage fields are present but all zero.

## Prompts, tool results and machinery

A `user` record with string content, or text blocks, is a prompt. A `user` record whose content
holds `tool_result` blocks is the result of the tool call the previous assistant record asked for;
its `tool_use_id` links it back to the call and therefore to a tool name.

Some `user` records are not the person typing:

- The compaction summary starts with a fixed sentence about the session being continued from a
  previous conversation, and newer releases also flag it with `isCompactSummary`.
- Slash commands and their local output appear wrapped in `<command-name>` and
  `<local-command-stdout>` tags.
- Records flagged `isMeta` are internal.

The parser classifies each prompt as `user`, `compaction_summary`, `command`, `reminder` or
`empty` so that metrics can count real prompts separately from machinery.

## Compaction

A compaction writes a `system` record with `subtype: "compact_boundary"` and:

```
compactMetadata.trigger                  "auto" or "manual"
compactMetadata.preTokens                context size before
compactMetadata.postTokens               context size after
compactMetadata.cumulativeDroppedTokens
compactMetadata.durationMs               how long the summarisation took
compactMetadata.preservedSegment         which recent messages were carried over verbatim
```

It is followed by the summary as a `user` record: a fixed opening sentence, then numbered
sections covering the request and intent, key technical concepts, files and code, errors and
fixes, pending tasks and current work. The pre-compaction records stay in the file, so the whole
history remains available for analysis.

Two related events leave no boundary record. Claude Code clears older tool outputs before it
resorts to summarising; that shows only as a fall in the next call's context size. And a session
forked with `/branch` or `--fork-session` starts its own file with the history copied in, so its
first call already carries a large context.

## Attachments

Attachment records log context Claude Code injects around the conversation. Kinds observed:

| kind | Content |
|---|---|
| `prompt_snapshot` | The system prompt, recorded when it is built or rebuilt; once per session in the common case |
| `instructions` | Instruction files in effect (user and project `CLAUDE.md`), with their text |
| `skill_listing` | The list of available skills and their descriptions |
| `deferred_tools_delta`, `agent_listing_delta`, `mcp_instructions_delta` | Tool, agent and MCP listings as they change |
| `edited_text_file` | The new contents of a file the model had read that changed on disk |
| `file` | A file attached to a prompt |
| `queued_command` | Prompts queued while the model was working |
| `total_tokens_reminder`, `batching_reminder_sent`, `task_reminder`, `bash_output_audience_note` | Per-turn reminders |
| `environment`, `model`, `date`, `session_context` | Session facts, once per session |

When present, `rendered` holds the text as the model sees it, and the parser measures that.
