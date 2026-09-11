"""Measurements derived from a parsed ``Session``.

Definitions (see docs/metrics.md for the rationale):

* context size      tokens the model was given on an API call: input + cache read + cache creation
* baseline context  context size on the first call of a session: system prompt, instruction
                    files, tool schemas and listings, before any conversation happens
* prompt cost       tokens the context grew by while one prompt was being handled: the sum of
                    positive call-to-call growth plus the output of the final call
* composition       an estimate, from character counts, of what the context is made of
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from typing import Callable, Iterable

from .records import ApiCall, Session, parse_ts

LISTING_KINDS = {"deferred_tools_delta", "agent_listing_delta", "skill_listing", "mcp_instructions_delta"}
CHARS_PER_TOKEN = 4  # rough English/code average, used only for composition estimates
CONTEXT_LIMIT = 1_000_000  # window size the observed sessions ran against; see docs/metrics.md
MIN_FILLS_FOR_RATE = 0.5  # below this a prompts-per-fill figure would be extrapolating from too little


DROP_FRACTION = 0.10  # a call-to-call fall in context this large is recorded as a drop


def context_drops(s: Session, fraction: float = DROP_FRACTION) -> list[dict]:
    """Falls in context size between consecutive calls that no compaction explains.

    The window can shrink without a full compaction: Claude Code clears old tool results when
    space runs low, and a user can rewind to an earlier message. Both show up as cliffs in the
    context curve with no ``compact_boundary`` record beside them.
    """
    after_compaction = {c.api_call_index for c in s.compactions}
    rows = []
    for a, b in zip(s.api_calls, s.api_calls[1:]):
        fall = a.usage.context - b.usage.context
        if fall <= 0 or fall < a.usage.context * fraction or b.index in after_compaction:
            continue
        rows.append({
            "session": s.session_id,
            "project": s.project_slug,
            "call": b.index,
            "timestamp": b.timestamp,
            "prompt_index": b.prompt_index,
            "model_before": a.model,
            "model_after": b.model,
            "before": a.usage.context,
            "after": b.usage.context,
            "dropped": fall,
            "dropped_pct": round(100 * fall / a.usage.context, 1),
        })
    return rows


def window_fills(s: Session, limit: int = CONTEXT_LIMIT) -> float:
    """How many times the session filled its window: compactions so far plus the current fill."""
    if not s.api_calls:
        return 0.0
    return len(s.compactions) + s.api_calls[-1].usage.context / limit


def dominant(counter: Counter) -> str | None:
    return counter.most_common(1)[0][0] if counter else None


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    vs = sorted(values)
    k = (len(vs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(vs) - 1)
    return vs[lo] + (vs[hi] - vs[lo]) * (k - lo)


def describe(values: Iterable[float]) -> dict:
    vs = [v for v in values if v is not None]
    if not vs:
        return {"n": 0, "median": None, "p90": None, "mean": None, "total": 0}
    return {"n": len(vs), "median": statistics.median(vs), "p90": percentile(vs, 0.9),
            "mean": statistics.fmean(vs), "total": sum(vs)}


def _seconds_between(a: str | None, b: str | None) -> float | None:
    da, db = parse_ts(a), parse_ts(b)
    return (db - da).total_seconds() if da and db else None


def calls_by_prompt(s: Session) -> dict[int, list[ApiCall]]:
    groups: dict[int, list[ApiCall]] = defaultdict(list)
    for c in s.api_calls:
        groups[c.prompt_index].append(c)
    return groups


def session_summary(s: Session) -> dict:
    ctx = [c.usage.context for c in s.api_calls]
    tool_chars_by_name: Counter = Counter()
    for r in s.tool_results:
        tool_chars_by_name[r.tool_name] += r.chars
    fills = window_fills(s)
    prompts = len(s.user_prompts)
    drops = context_drops(s)
    return {
        "project": s.project_slug,
        "session": s.session_id,
        "date": (s.first_ts or "")[:10],
        "duration_min": round((_seconds_between(s.first_ts, s.last_ts) or 0) / 60, 1),
        "model": dominant(s.models),
        "models": ",".join(sorted(s.models)),
        "effort": dominant(s.efforts),
        "version": dominant(s.versions),
        "prompts": prompts,
        "api_calls": len(s.api_calls),
        "tool_calls": len(s.tool_uses),
        "tool_errors": sum(1 for r in s.tool_results if r.is_error),
        "tool_result_chars": sum(r.chars for r in s.tool_results),
        "output_tokens": sum(c.usage.output for c in s.api_calls),
        "thinking_tokens": sum(c.usage.thinking for c in s.api_calls),
        "baseline_context": ctx[0] if ctx else None,
        "peak_context": max(ctx) if ctx else None,
        "final_context": ctx[-1] if ctx else None,
        "compactions": len(s.compactions),
        "window_fills": round(fills, 2),
        "prompts_per_fill": round(prompts / fills, 1) if fills >= MIN_FILLS_FOR_RATE else None,
        "context_drops": len(drops),
        "dropped_without_compaction": sum(d["dropped"] for d in drops),
        "subagents": len(s.subagents),
        "subagent_api_calls": sum(a.api_calls for a in s.subagents),
        "subagent_output_tokens": sum(a.output_tokens for a in s.subagents),
        "top_tools": ", ".join(f"{k}:{v}" for k, v in Counter(t.name for t in s.tool_uses).most_common(5)),
        "top_tool_result_chars": ", ".join(f"{k}:{v}" for k, v in tool_chars_by_name.most_common(5)),
    }


def context_curve(s: Session) -> list[dict]:
    return [{"call": c.index, "timestamp": c.timestamp, "prompt_index": c.prompt_index,
             "context": c.usage.context, "output": c.usage.output, "model": c.model}
            for c in s.api_calls]


def prompt_costs(s: Session) -> list[dict]:
    """One row per turn-starting prompt, describing how much context handling it consumed."""
    groups = calls_by_prompt(s)
    tools_by_prompt: Counter = Counter(t.prompt_index for t in s.tool_uses)
    result_chars: Counter = Counter()
    for r in s.tool_results:
        result_chars[r.prompt_index] += r.chars
    compaction_prompts = {c.prompt_index for c in s.compactions}
    rows: list[dict] = []
    seen: set[int] = set()
    for p in s.prompts:
        if p.kind not in ("user", "compaction_summary", "command") or p.index in seen:
            continue
        seen.add(p.index)
        calls = groups.get(p.index, [])
        added = 0
        for a, b in zip(calls, calls[1:]):
            added += max(0, b.usage.context - a.usage.context)
        if calls:
            added += calls[-1].usage.output
        rows.append({
            "session": s.session_id,
            "project": s.project_slug,
            "prompt_index": p.index,
            "kind": p.kind,
            "timestamp": p.timestamp,
            "prompt_chars": p.chars,
            "model": calls[0].model if calls else None,
            "effort": calls[0].effort if calls else None,
            "version": calls[0].version if calls else None,
            "api_calls": len(calls),
            "tool_calls": tools_by_prompt.get(p.index, 0),
            "tool_result_chars": result_chars.get(p.index, 0),
            "context_start": calls[0].usage.context if calls else None,
            "context_end": (calls[-1].usage.context + calls[-1].usage.output) if calls else None,
            "added_tokens": added,
            "output_tokens": sum(c.usage.output for c in calls),
            "thinking_tokens": sum(c.usage.thinking for c in calls),
            "duration_s": _seconds_between(p.timestamp, calls[-1].timestamp) if calls else None,
            "compaction": p.index in compaction_prompts,
        })
    return rows


def composition(s: Session) -> list[dict]:
    """Estimated make-up of everything that entered the context, by source."""
    buckets: Counter = Counter()
    for a in s.attachments:
        if a.kind == "prompt_snapshot":
            buckets["system prompt"] += a.chars
        elif a.kind == "instructions":
            buckets["instruction files"] += a.chars
        elif a.kind in LISTING_KINDS:
            buckets["tool, agent and skill listings"] += a.chars
        else:
            buckets["reminders and environment"] += a.chars
    for p in s.prompts:
        if p.kind == "user":
            buckets["user prompts"] += p.chars
        elif p.kind == "compaction_summary":
            buckets["compaction summaries"] += p.chars
        elif p.kind == "command":
            buckets["local command output"] += p.chars
    for c in s.api_calls:
        buckets["assistant text"] += c.text_chars
        buckets["assistant thinking"] += c.thinking_chars
    for t in s.tool_uses:
        buckets["tool call inputs"] += t.input_chars
    for r in s.tool_results:
        buckets[f"tool results: {r.tool_name}"] += r.chars
    total = sum(buckets.values()) or 1
    return [{"source": k, "chars": v, "est_tokens": v // CHARS_PER_TOKEN, "share": v / total}
            for k, v in buckets.most_common()]


def compaction_rows(s: Session) -> list[dict]:
    n_calls = len(s.api_calls)
    last_prompt = max((p.index for p in s.prompts), default=0)
    rows = []
    for c in s.compactions:
        model = s.api_calls[c.api_call_index - 1].model if 0 < c.api_call_index <= n_calls else dominant(s.models)
        rows.append({
            "session": s.session_id,
            "project": s.project_slug,
            "timestamp": c.timestamp,
            "model": model,
            "trigger": c.trigger,
            "prompt_index": c.prompt_index,
            "api_call_index": c.api_call_index,
            "pre_tokens": c.pre_tokens,
            "post_tokens": c.post_tokens,
            "retained_pct": round(100 * c.retained_fraction, 1),
            "duration_s": round(c.duration_ms / 1000, 1),
            "summary_chars": c.summary_chars,
            "calls_after": n_calls - c.api_call_index,
            "prompts_after": last_prompt - c.prompt_index,
        })
    return rows


def aggregate_prompt_costs(rows: list[dict], by: str | Callable[[dict], str] = "model",
                           min_calls: int = 1) -> list[dict]:
    """Per-group distribution of prompt costs, for prompts that actually reached the model."""
    key = by if callable(by) else (lambda r: str(r.get(by)))
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["api_calls"] >= min_calls:
            groups[key(r)].append(r)
    out = []
    for g, rs in sorted(groups.items()):
        added = describe(r["added_tokens"] for r in rs)
        calls = describe(r["api_calls"] for r in rs)
        tools = describe(r["tool_calls"] for r in rs)
        tchars = describe(r["tool_result_chars"] for r in rs)
        outp = describe(r["output_tokens"] for r in rs)
        out.append({
            "group": g,
            "prompts": len(rs),
            "sessions": len({r["session"] for r in rs}),
            "added_tokens_median": added["median"],
            "added_tokens_p90": added["p90"],
            "api_calls_median": calls["median"],
            "api_calls_p90": calls["p90"],
            "tool_calls_median": tools["median"],
            "tool_result_chars_median": tchars["median"],
            "output_tokens_median": outp["median"],
        })
    return out


def baseline_by(sessions: list[Session], key: str = "version") -> list[dict]:
    groups: dict[str, list[int]] = defaultdict(list)
    for s in sessions:
        if not s.api_calls:
            continue
        first = s.api_calls[0]
        k = {"version": first.version, "model": first.model, "effort": first.effort}.get(key) or "unknown"
        groups[str(k)].append(first.usage.context)
    return [{"group": g, **describe(vs)} for g, vs in sorted(groups.items())]
