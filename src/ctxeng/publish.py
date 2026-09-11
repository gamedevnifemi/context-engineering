"""Aggregate-only report for publication.

The default report keeps per-session detail for local analysis. This variant publishes only
distributions and ranges: no per-session rows, no session identifiers, and example charts
labelled by model alone. Groups backed by very few sessions are omitted because they are
single-session rows in disguise. See docs/privacy.md.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from . import metrics
from .records import Session
from .report import md_table, published_composition

MIN_GROUP_SESSIONS = 3


def _span(values, fmt=lambda v: f"{v:,.0f}") -> str:
    vs = sorted(v for v in values if v is not None)
    if not vs:
        return ""
    return fmt(vs[0]) if vs[0] == vs[-1] else f"{fmt(vs[0])} to {fmt(vs[-1])}"


def fills_by_model(summaries: list[dict]) -> list[dict]:
    groups: dict[str, list[float]] = defaultdict(list)
    for s in summaries:
        if s.get("prompts_per_fill") is not None:
            groups[str(s.get("model"))].append(s["prompts_per_fill"])
    return [{"model": m, "sessions": len(v), "min": min(v), "median": statistics.median(v), "max": max(v)}
            for m, v in sorted(groups.items())]


def compactions_by_trigger(rows: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[str(r.get("trigger"))].append(r)
    out = []
    for trigger, rs in sorted(groups.items()):
        out.append({
            "trigger": trigger,
            "events": len(rs),
            "tokens before": _span(r["pre_tokens"] for r in rs),
            "tokens after": _span(r["post_tokens"] for r in rs),
            "retained": _span((r["retained_pct"] for r in rs), lambda v: f"{v:.1f}%"),
            "duration": _span((r["duration_s"] / 60 for r in rs), lambda v: f"{v:.1f} min"),
            "summary size": _span((r["summary_chars"] / 1000 for r in rs), lambda v: f"{v:.0f}k chars"),
        })
    return out


def drops_summary(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    switches = [r for r in rows if r["model_before"] != r["model_after"]]
    return [{
        "drops": len(rows),
        "with a model switch": len(switches),
        "size": _span((r["dropped_pct"] for r in rows), lambda v: f"{v:.0f}%"),
        "size when switching": _span((r["dropped_pct"] for r in switches), lambda v: f"{v:.0f}%"),
    }]


def aggregate_composition(sessions: list[Session], top: int) -> tuple[list[dict], int]:
    """Share of characters by source over the largest sessions.

    The median of per-session shares describes a typical session; the pooled share weights
    sessions by volume and can be dominated by one very large session. Both are reported.
    """
    largest = sorted(sessions, key=lambda s: len(s.api_calls), reverse=True)[:top]
    comps = [published_composition(s) for s in largest]
    sources: list[str] = []
    totals: Counter = Counter()
    for comp in comps:
        for r in comp:
            if r["source"] not in sources:
                sources.append(r["source"])
            totals[r["source"]] += r["chars"]
    total = sum(totals.values()) or 1
    rows = []
    for source in sources:
        shares = [100 * next((r["share"] for r in comp if r["source"] == source), 0.0) for comp in comps]
        rows.append({
            "source": source,
            "median_session_pct": round(statistics.median(shares), 1) if shares else 0.0,
            "pooled_pct": round(100 * totals[source] / total, 1),
            "range across sessions": _span(shares, lambda v: f"{v:.0f}%"),
        })
    rows.sort(key=lambda r: (r["median_session_pct"], r["pooled_pct"]), reverse=True)
    return rows, len(largest)


def _enough(rows: list[dict], key: str = "sessions") -> list[dict]:
    return [r for r in rows if (r.get(key) or 0) >= MIN_GROUP_SESSIONS]


def build_publish_report(sessions: list[Session], out_dir: Path, *, charts: bool = False,
                         top: int = 6, min_calls: int = 5) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    started = [s for s in sessions if s.api_calls]  # every session that reached the model at all
    sessions = [s for s in sessions if len(s.api_calls) >= min_calls]
    summaries = [metrics.session_summary(s) for s in sessions]
    prompts = [r for s in sessions for r in metrics.prompt_costs(s)]
    compactions = [r for s in sessions for r in metrics.compaction_rows(s)]
    drops = [r for s in sessions for r in metrics.context_drops(s)]

    by_model = _enough(metrics.aggregate_prompt_costs(prompts, "model"))
    by_effort = _enough(metrics.aggregate_prompt_costs(prompts, "effort"))
    by_version = _enough(metrics.aggregate_prompt_costs(prompts, "version"))
    by_kind = metrics.aggregate_prompt_costs(
        [r for r in prompts if r["kind"] in ("user", "compaction_summary")], "kind")
    baseline = _enough(metrics.baseline_by(started, "model"), "n")
    composition, pooled = aggregate_composition(sessions, top)
    models_shown = {r["group"] for r in by_model}

    agg_cols = ["group", "sessions", "prompts", "added_tokens_median", "added_tokens_p90",
                "api_calls_median", "api_calls_p90", "tool_calls_median",
                "tool_result_chars_median", "output_tokens_median"]
    lines = [
        "# Context usage report (publishable)",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d')} from {len(sessions)} sessions with "
        f"at least {min_calls} API calls. Aggregates and ranges only; groups backed by fewer than "
        f"{MIN_GROUP_SESSIONS} sessions are omitted.",
        "",
        "## Prompts per window fill, by model",
        "",
        f"Over sessions that filled at least half of the {metrics.CONTEXT_LIMIT:,}-token window.",
        "",
        md_table(fills_by_model(summaries), ["model", "sessions", "min", "median", "max"]),
        "## Context growth per prompt, by model",
        "",
        md_table(by_model, agg_cols),
        "## Context growth per prompt, by effort level",
        "",
        md_table(by_effort, agg_cols),
        "## Context growth per prompt, by Claude Code version",
        "",
        md_table(by_version, agg_cols),
        "## Cost of the first turn after a compaction",
        "",
        md_table(by_kind, agg_cols),
        "## Baseline context at session start, by model",
        "",
        f"Over the {len(started)} sessions that made at least one call.",
        "",
        md_table(baseline, ["group", "n", "median", "p90", "mean"]),
        "## Compactions, by trigger",
        "",
        md_table(compactions_by_trigger(compactions)),
        "## Context drops without a compaction",
        "",
        md_table(drops_summary(drops)),
        f"## What filled the context, over the {pooled} largest sessions",
        "",
        "`median_session_pct` is the median of per-session shares; `pooled_pct` weights sessions by volume.",
        "",
        md_table(composition[:12], ["source", "median_session_pct", "pooled_pct", "range across sessions"]),
    ]
    if charts:
        made = render_publish_charts(sessions, prompts, out_dir, models_shown)
        lines += ["## Charts", ""] + ([f"![{p.stem}]({p.name})\n" for p in made] or
                                      ["_matplotlib not available; charts skipped._", ""])
    report = out_dir / "report.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    return report


def render_publish_charts(sessions: list[Session], prompts: list[dict], out_dir: Path,
                          models_shown: set[str]) -> list[Path]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    made: list[Path] = []

    # Two illustrative sessions, labelled by model only: the one with the most compactions and
    # the largest that never compacted.
    with_comp = max(sessions, key=lambda s: (len(s.compactions), len(s.api_calls)), default=None)
    without = max((s for s in sessions if not s.compactions and s is not with_comp),
                  key=lambda s: len(s.api_calls), default=None)
    examples = [s for s in (with_comp, without) if s is not None]
    if examples:
        fig, axes = plt.subplots(1, len(examples), figsize=(6 * len(examples), 3.4), squeeze=False)
        for ax, s, letter in zip(axes.flat, examples, "AB"):
            curve = metrics.context_curve(s)
            ax.plot([c["call"] for c in curve], [c["context"] / 1000 for c in curve], lw=1.2)
            for c in s.compactions:
                ax.axvline(c.api_call_index, color="tab:red", ls="--", lw=1)
            n = len(s.compactions)
            ax.set_title(f"Example {letter}: {metrics.dominant(s.models)}, "
                         f"{n} compaction{'s' if n != 1 else ''}", fontsize=9)
            ax.set_xlabel("API call")
            ax.set_ylabel("context (k tokens)")
        fig.suptitle("Context size over a session (red = compaction)")
        fig.tight_layout()
        p = out_dir / "context_examples.png"
        fig.savefig(p, dpi=130)
        plt.close(fig)
        made.append(p)

    groups: dict[str, list[int]] = {}
    for r in prompts:
        if r["api_calls"] >= 1 and r["model"] in models_shown:
            groups.setdefault(r["model"], []).append(max(r["added_tokens"], 1))
    if groups:
        fig, ax = plt.subplots(figsize=(7, 3.6))
        labels = sorted(groups)
        ax.boxplot([groups[k] for k in labels], tick_labels=labels, showfliers=False)
        ax.set_yscale("log")
        ax.set_ylabel("tokens added per prompt (log)")
        ax.set_title("Context growth per prompt, by model")
        fig.tight_layout()
        p = out_dir / "growth_by_model.png"
        fig.savefig(p, dpi=130)
        plt.close(fig)
        made.append(p)

    rows, pooled = aggregate_composition(sessions, top=6)
    if rows:
        rows = rows[:10]
        fig, ax = plt.subplots(figsize=(7, 3.8))
        ax.barh([r["source"] for r in rows][::-1], [r["median_session_pct"] for r in rows][::-1])
        ax.set_xlabel("median share of characters that entered the context (%)")
        ax.set_title(f"What filled the context, typical of the {pooled} largest sessions")
        fig.tight_layout()
        p = out_dir / "composition.png"
        fig.savefig(p, dpi=130)
        plt.close(fig)
        made.append(p)
    return made
