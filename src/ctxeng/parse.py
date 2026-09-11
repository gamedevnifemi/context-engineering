"""Stream a transcript file into a ``Session``.

Transcripts are JSON Lines. The records that matter for context accounting are:

* ``user``       a prompt, a tool result, or the summary that opens a post-compaction context
* ``assistant``  one content block of a model response; blocks of the same response share a
                 ``requestId`` and repeat the same usage figures, so usage is counted once per id
* ``system``     control records; ``compact_boundary`` carries the compaction metadata
* ``attachment`` context injected by Claude Code: system prompt, instruction files, tool and
                 skill listings, date and token reminders

Everything else (mode changes, titles, queue bookkeeping) is counted but otherwise ignored.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from .locate import SessionRef
from .records import (ApiCall, Attachment, Compaction, Prompt, Session, SubagentSummary,
                      ToolResult, ToolUse, Usage)

CONTINUATION_PREFIX = "This session is being continued from a previous conversation"
_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
_COMMAND_MARKERS = ("<command-name>", "<local-command-stdout>", "<local-command-caveat>")


def _chars(value) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value)
    try:
        return len(json.dumps(value, ensure_ascii=False))
    except TypeError:
        return len(str(value))


def _attachment_chars(att: dict, rendered) -> int:
    """Size of an attachment as the model sees it, preferring the rendered form."""
    if isinstance(rendered, list) and rendered:
        return sum(len(r.get("content", "")) for r in rendered if isinstance(r, dict))
    kind = att.get("type")
    if kind == "prompt_snapshot":
        return sum(len(s) for s in att.get("systemPrompt") or [] if isinstance(s, str))
    if kind == "instructions":
        return sum(len(f.get("content", "")) for f in att.get("files") or [] if isinstance(f, dict))
    for key in ("content", "text"):
        if isinstance(att.get(key), str):
            return len(att[key])
    for key in ("addedLines", "addedBlocks"):
        if isinstance(att.get(key), list):
            return sum(len(x) for x in att[key] if isinstance(x, str))
    return _chars(att)


def classify_prompt(text: str, record: dict) -> str:
    if record.get("isCompactSummary") or text.startswith(CONTINUATION_PREFIX):
        return "compaction_summary"
    if any(marker in text for marker in _COMMAND_MARKERS):
        return "command"
    if not _REMINDER.sub("", text).strip():
        return "reminder" if text.strip() else "empty"
    return "user"


def parse_session(ref: SessionRef | Path | str, *, include_subagents: bool = True) -> Session:
    if isinstance(ref, SessionRef):
        path, slug, sid, subs = ref.path, ref.project_slug, ref.session_id, ref.subagent_paths
    else:
        path = Path(ref)
        slug, sid, subs = path.parent.name, path.stem, ()
    session = Session(project_slug=slug, session_id=sid, path=str(path))
    _parse_into(session, path)
    if include_subagents:
        for sub_path in subs:
            sub = Session(project_slug=slug, session_id=sub_path.stem, path=str(sub_path))
            _parse_into(sub, sub_path)
            session.subagents.append(summarize_subagent(sub))
    return session


def parse_many(refs: Iterable[SessionRef], **kw) -> list[Session]:
    return [parse_session(r, **kw) for r in refs]


def summarize_subagent(s: Session) -> SubagentSummary:
    return SubagentSummary(
        agent_id=s.session_id,
        api_calls=len(s.api_calls),
        output_tokens=sum(c.usage.output for c in s.api_calls),
        thinking_tokens=sum(c.usage.thinking for c in s.api_calls),
        peak_context=max((c.usage.context for c in s.api_calls), default=0),
        tool_uses=len(s.tool_uses),
        models=s.models,
    )


def _parse_into(s: Session, path: Path) -> None:
    calls_by_request: dict[str, ApiCall] = {}
    tool_names: dict[str, str] = {}
    prompt_index = 0
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                s.record_types["<unparseable>"] += 1
                continue
            if not isinstance(rec, dict):
                continue
            rtype = rec.get("type")
            s.record_types[rtype] += 1
            ts = rec.get("timestamp")
            if ts:
                s.first_ts = s.first_ts or ts
                s.last_ts = ts
            if rtype == "user":
                prompt_index = _user(s, rec, prompt_index, tool_names)
            elif rtype == "assistant":
                _assistant(s, rec, prompt_index, calls_by_request, tool_names)
            elif rtype == "system":
                _system(s, rec, prompt_index)
            elif rtype == "attachment":
                att = rec.get("attachment") or {}
                s.attachments.append(Attachment(att.get("type", "unknown"),
                                                _attachment_chars(att, rec.get("rendered")),
                                                prompt_index, ts or ""))


def _user(s: Session, rec: dict, prompt_index: int, tool_names: dict[str, str]) -> int:
    if rec.get("isMeta"):
        return prompt_index
    content = (rec.get("message") or {}).get("content")
    ts = rec.get("timestamp") or ""
    if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result"
                                         for b in content):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                tid = b.get("tool_use_id", "")
                s.tool_results.append(ToolResult(tid, tool_names.get(tid, "unknown"),
                                                 _chars(b.get("content")), bool(b.get("is_error")),
                                                 prompt_index, ts))
        return prompt_index
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = "".join(b.get("text", "") for b in content
                       if isinstance(b, dict) and b.get("type") == "text")
    else:
        text = ""
    kind = classify_prompt(text, rec)
    if kind in ("user", "compaction_summary", "command"):
        prompt_index += 1
    s.prompts.append(Prompt(prompt_index, ts, len(text), kind))
    if kind == "compaction_summary" and s.compactions and s.compactions[-1].summary_chars == 0:
        s.compactions[-1].summary_chars = len(text)
    return prompt_index


def _assistant(s: Session, rec: dict, prompt_index: int,
               calls_by_request: dict[str, ApiCall], tool_names: dict[str, str]) -> None:
    msg = rec.get("message") or {}
    model = msg.get("model") or "unknown"
    if model == "<synthetic>":
        s.record_types["assistant:synthetic"] += 1  # local error/notice messages, not model output
        return
    rid = rec.get("requestId") or msg.get("id") or f"anon-{len(s.api_calls)}"
    usage = Usage.from_api(msg.get("usage") or {})
    call = calls_by_request.get(rid)
    if call is None:
        call = ApiCall(index=len(s.api_calls), request_id=rid, timestamp=rec.get("timestamp") or "",
                       model=model, effort=rec.get("effort"), version=rec.get("version"),
                       usage=usage, stop_reason=msg.get("stop_reason"), prompt_index=prompt_index)
        s.api_calls.append(call)
        calls_by_request[rid] = call
        s.models[model] += 1
        if call.effort:
            s.efforts[call.effort] += 1
        if call.version:
            s.versions[call.version] += 1
    else:
        call.usage.merge_max(usage)
        if msg.get("stop_reason"):
            call.stop_reason = msg.get("stop_reason")
    for b in msg.get("content") or []:
        if not isinstance(b, dict):
            continue
        btype = b.get("type")
        if btype == "text":
            call.text_chars += len(b.get("text", ""))
        elif btype == "thinking":
            call.thinking_chars += len(b.get("thinking", ""))
        elif btype == "tool_use":
            tu = ToolUse(b.get("id", ""), b.get("name", "unknown"), _chars(b.get("input")),
                         rid, prompt_index, call.timestamp)
            call.tool_uses.append(tu)
            s.tool_uses.append(tu)
            tool_names[tu.id] = tu.name


def _system(s: Session, rec: dict, prompt_index: int) -> None:
    subtype = rec.get("subtype") or "unknown"
    s.system_subtypes[subtype] += 1
    if subtype != "compact_boundary":
        return
    meta = rec.get("compactMetadata") or {}
    s.compactions.append(Compaction(
        timestamp=rec.get("timestamp") or "",
        trigger=meta.get("trigger") or "unknown",
        pre_tokens=int(meta.get("preTokens") or 0),
        post_tokens=int(meta.get("postTokens") or 0),
        dropped_tokens=int(meta.get("cumulativeDroppedTokens") or 0),
        duration_ms=int(meta.get("durationMs") or 0),
        prompt_index=prompt_index,
        api_call_index=len(s.api_calls),
    ))
