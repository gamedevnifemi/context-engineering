"""Build small synthetic transcripts. Nothing here comes from a real session."""
from __future__ import annotations

import json
from pathlib import Path

SESSION_ID = "11111111-2222-3333-4444-555555555555"
PROJECT_SLUG = "D--work-demo"  # a project outside any home directory, so no username is embedded


def _rec(rtype: str, ts: str, **extra) -> dict:
    base = {"type": rtype, "timestamp": ts, "sessionId": SESSION_ID, "isSidechain": False,
            "cwd": "D:\\work\\demo", "version": "9.9.9"}
    base.update(extra)
    return base


def user(ts, text, **extra):
    return _rec("user", ts, message={"role": "user", "content": text}, **extra)


def tool_result(ts, tool_use_id, content, is_error=False):
    return _rec("user", ts, message={"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_use_id, "content": content, "is_error": is_error}]})


def assistant(ts, request_id, blocks, usage, model="claude-demo", effort="high", stop="end_turn"):
    """One record per content block, all sharing request id and usage, as Claude Code writes them."""
    out = []
    for i, b in enumerate(blocks):
        out.append(_rec("assistant", ts, requestId=request_id, apiBlockIndex=i, effort=effort,
                        message={"role": "assistant", "model": model, "stop_reason": stop,
                                 "content": [b], "usage": usage}))
    return out


def usage(context, output, cache_creation=None, thinking=0):
    cc = context if cache_creation is None else cache_creation
    return {"input_tokens": 1, "cache_read_input_tokens": context - cc - 1,
            "cache_creation_input_tokens": cc, "output_tokens": output,
            "output_tokens_details": {"thinking_tokens": thinking}}


def attachment(ts, kind, **payload):
    return _rec("attachment", ts, attachment={"type": kind, **payload})


def compact_boundary(ts, pre, post, trigger="auto"):
    return _rec("system", ts, subtype="compact_boundary", content="Conversation compacted",
                compactMetadata={"trigger": trigger, "preTokens": pre, "postTokens": post,
                                 "cumulativeDroppedTokens": pre - post, "durationMs": 4200})


def demo_records() -> list[dict]:
    """Three prompts: a plain answer, a tool-using turn, and a compaction followed by more work."""
    r: list[dict] = []
    r.append(attachment("2026-01-01T10:00:00.000Z", "prompt_snapshot", systemPrompt=["x" * 4000]))
    r.append(attachment("2026-01-01T10:00:00.001Z", "instructions",
                        files=[{"path": "CLAUDE.md", "type": "Project", "content": "y" * 800}]))
    r.append(attachment("2026-01-01T10:00:00.002Z", "skill_listing", content="z" * 1200))
    r.append(user("2026-01-01T10:00:01.000Z", "hello, what does this repo do?"))
    r += assistant("2026-01-01T10:00:05.000Z", "req_1",
                   [{"type": "thinking", "thinking": "t" * 100}, {"type": "text", "text": "It is a demo."}],
                   usage(context=20_000, output=300, cache_creation=20_000, thinking=80))
    r.append(user("2026-01-01T10:01:00.000Z", "list the files"))
    r += assistant("2026-01-01T10:01:03.000Z", "req_2",
                   [{"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "ls"}}],
                   usage(context=20_400, output=60, cache_creation=400), stop="tool_use")
    r.append(tool_result("2026-01-01T10:01:04.000Z", "toolu_1", "a.py\nb.py\n" * 200))
    r += assistant("2026-01-01T10:01:09.000Z", "req_3", [{"type": "text", "text": "Two files."}],
                   usage(context=21_500, output=40, cache_creation=1_100))
    r.append(compact_boundary("2026-01-01T10:02:00.000Z", pre=21_540, post=3_000))
    r.append(user("2026-01-01T10:02:01.000Z",
                  "This session is being continued from a previous conversation that ran out of context. "
                  + "s" * 2000))
    r += assistant("2026-01-01T10:02:05.000Z", "req_4", [{"type": "text", "text": "Continuing."}],
                   usage(context=3_600, output=20, cache_creation=3_600))
    r.append(user("2026-01-01T10:03:00.000Z", "<command-name>/status</command-name>"))
    r.append(user("2026-01-01T10:03:00.100Z", "<local-command-stdout>ok</local-command-stdout>"))
    r.append(_rec("ai-title", "2026-01-01T10:03:01.000Z", aiTitle="demo"))
    return r


def write_store(root: Path) -> Path:
    """Create a fake projects directory with one session and one subagent transcript."""
    proj = root / PROJECT_SLUG
    proj.mkdir(parents=True)
    main = proj / f"{SESSION_ID}.jsonl"
    main.write_text("\n".join(json.dumps(x) for x in demo_records()) + "\n", encoding="utf-8")
    side = proj / SESSION_ID / "subagents"
    side.mkdir(parents=True)
    sub = [user("2026-01-01T10:01:05.000Z", "research something", isSidechain=True, agentId="abc")]
    sub += assistant("2026-01-01T10:01:07.000Z", "req_s1", [{"type": "text", "text": "done"}],
                     usage(context=9_000, output=500, cache_creation=9_000))
    (side / "agent-abc.jsonl").write_text("\n".join(json.dumps(x) for x in sub) + "\n", encoding="utf-8")
    return root
