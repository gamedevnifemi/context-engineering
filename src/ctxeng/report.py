"""Turn parsed sessions into a shareable report: CSVs, a Markdown summary, optional charts.

Every project and session identifier in the output is a pseudonym from ``ctxeng.redact``.
Charts need matplotlib; everything else is standard library.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from . import metrics
from .records import Session
from .redact import project_alias, session_alias


def _alias_row(row: dict) -> dict:
    out = dict(row)
    if "project" in out:
        out["project"] = project_alias(out["project"])
    if "session" in out:
        out["session"] = session_alias(out["session"])
    return out


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "yes" if v else ""
    if isinstance(v, float):
        return f"{v:,.1f}" if abs(v) < 100 else f"{v:,.0f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def md_table(rows: list[dict], columns: list[str] | None = None) -> str:
    if not rows:
        return "_no data_\n"
    cols = columns or list(rows[0].keys())
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(_fmt(r.get(c)) for c in cols) + " |")
    return "\n".join(lines) + "\n"


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def build_report(sessions: list[Session], out_dir: Path, *, charts: bool = False,
                 top: int = 6, min_calls: int = 5) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    sessions = [s for s in sessions if len(s.api_calls) >= min_calls]

    summaries = [_alias_row(metrics.session_summary(s)) for s in sessions]
    prompts = [_alias_row(r) for s in sessions for r in metrics.prompt_costs(s)]
    compactions = [_alias_row(r) for s in sessions for r in metrics.compaction_rows(s)]
    drops = sorted((_alias_row(r) for s in sessions for r in metrics.context_drops(s)),
                   key=lambda r: r["dropped"], reverse=True)
    write_csv(out_dir / "sessions.csv", summaries)
    write_csv(out_dir / "prompts.csv", prompts)
    write_csv(out_dir / "compactions.csv", compactions)
    write_csv(out_dir / "context_drops.csv", drops)

    by_model = metrics.aggregate_prompt_costs(prompts, "model")
    by_effort = metrics.aggregate_prompt_costs(prompts, "effort")
    by_version = metrics.aggregate_prompt_costs(prompts, "version")
    by_kind = metrics.aggregate_prompt_costs(
        [r for r in prompts if r["kind"] in ("user", "compaction_summary")], "kind")
    baseline = metrics.baseline_by(sessions, "version")
    largest = sorted(sessions, key=lambda s: len(s.api_calls), reverse=True)[:top]
    fills = sorted((r for r in summaries if r["prompts_per_fill"] is not None), key=lambda r: r["date"])

    agg_cols = ["group", "sessions", "prompts", "added_tokens_median", "added_tokens_p90",
                "api_calls_median", "api_calls_p90", "tool_calls_median",
                "tool_result_chars_median", "output_tokens_median"]
    lines = [
        "# Context usage report",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from "
        f"{len(sessions)} sessions with at least {min_calls} API calls. Identifiers are pseudonyms.",
        "",
        "## Sessions by model",
        "",
        md_table(_count_by(summaries, "model"), ["group", "sessions", "prompts", "api_calls", "compactions"]),
        "## Prompts per window fill",
        "",
        f"How many user prompts it took to fill the {metrics.CONTEXT_LIMIT:,}-token window, for sessions "
        f"that filled at least half of it. `window_fills` counts compactions plus the current fill.",
        "",
        md_table(fills, ["date", "session", "model", "effort", "version", "prompts", "compactions",
                         "window_fills", "prompts_per_fill"]),
        "## Context growth per prompt, by model",
        "",
        "`added_tokens` is how much the context grew while one prompt was handled.",
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
        "`compaction_summary` rows are the turns that start from a compaction summary instead of a "
        "user prompt: the model re-orienting itself in a fresh window.",
        "",
        md_table(by_kind, agg_cols),
        "## Baseline context at session start, by Claude Code version",
        "",
        "Tokens already in the window on the very first call, before any conversation.",
        "",
        md_table(baseline, ["group", "n", "median", "p90", "mean"]),
        "## Compaction events",
        "",
        md_table(compactions, ["session", "model", "trigger", "prompt_index", "pre_tokens",
                               "post_tokens", "retained_pct", "duration_s", "summary_chars",
                               "calls_after", "prompts_after"]),
        "## Context drops without a compaction",
        "",
        f"Falls of at least {int(metrics.DROP_FRACTION * 100)}% between consecutive calls with no compaction "
        "record: tool-result clearing, rewinds, or something else worth explaining. Largest first.",
        "",
        md_table(drops[:15], ["session", "call", "prompt_index", "model_before", "model_after",
                              "before", "after", "dropped", "dropped_pct"]),
        "## Largest sessions",
        "",
        md_table([_alias_row(metrics.session_summary(s)) for s in largest],
                 ["session", "model", "effort", "version", "prompts", "api_calls", "tool_calls",
                  "baseline_context", "peak_context", "compactions", "subagents"]),
    ]
    for s in largest[:3]:
        lines += [f"## What filled the context: {session_alias(s.session_id)}", "",
                  md_table(_share_rows(metrics.composition(s)), ["source", "est_tokens", "share_pct"])]

    if charts:
        made = render_charts(sessions, prompts, out_dir, top=top)
        if made:
            lines += ["## Charts", ""] + [f"![{p.stem}]({p.name})\n" for p in made]
        else:
            lines += ["## Charts", "", "_matplotlib not available; charts skipped._", ""]

    report = out_dir / "report.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    return report


def _count_by(summaries: list[dict], key: str) -> list[dict]:
    groups: dict[str, dict] = {}
    for s in summaries:
        g = groups.setdefault(str(s.get(key)), {"group": str(s.get(key)), "sessions": 0,
                                                 "prompts": 0, "api_calls": 0, "compactions": 0})
        g["sessions"] += 1
        g["prompts"] += s["prompts"]
        g["api_calls"] += s["api_calls"]
        g["compactions"] += s["compactions"]
    return sorted(groups.values(), key=lambda g: g["group"])


def _share_rows(rows: list[dict], limit: int = 12) -> list[dict]:
    return [{**r, "share_pct": round(100 * r["share"], 1)} for r in rows[:limit]]


def render_charts(sessions: list[Session], prompts: list[dict], out_dir: Path, *, top: int = 6) -> list[Path]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    made: list[Path] = []

    largest = sorted(sessions, key=lambda s: len(s.api_calls), reverse=True)[:top]
    if largest:
        cols = 2 if len(largest) > 1 else 1
        rows_n = (len(largest) + cols - 1) // cols
        fig, axes = plt.subplots(rows_n, cols, figsize=(6 * cols, 3.2 * rows_n), squeeze=False)
        for ax, s in zip(axes.flat, largest):
            curve = metrics.context_curve(s)
            ax.plot([c["call"] for c in curve], [c["context"] / 1000 for c in curve], lw=1.2)
            for c in s.compactions:
                ax.axvline(c.api_call_index, color="tab:red", ls="--", lw=1)
            ax.set_title(f"{session_alias(s.session_id)}  ({metrics.dominant(s.models)})", fontsize=9)
            ax.set_xlabel("API call")
            ax.set_ylabel("context (k tokens)")
        for ax in list(axes.flat)[len(largest):]:
            ax.axis("off")
        fig.suptitle("Context size over a session (red = compaction)")
        fig.tight_layout()
        p = out_dir / "context_curves.png"
        fig.savefig(p, dpi=130)
        plt.close(fig)
        made.append(p)

    groups: dict[str, list[int]] = {}
    for r in prompts:
        if r["api_calls"] >= 1 and r["model"]:
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

    if largest:
        fig, ax = plt.subplots(figsize=(8, 3.8))
        names = [session_alias(s.session_id) for s in largest]
        comps = [metrics.composition(s) for s in largest]
        top_sources: list[str] = []
        for comp in comps:
            for r in comp[:6]:
                if r["source"] not in top_sources:
                    top_sources.append(r["source"])
        bottoms = [0.0] * len(largest)
        for src in top_sources:
            vals = [next((r["share"] * 100 for r in comp if r["source"] == src), 0.0) for comp in comps]
            ax.bar(names, vals, bottom=bottoms, label=src)
            bottoms = [b + v for b, v in zip(bottoms, vals)]
        ax.bar(names, [100 - b for b in bottoms], bottom=bottoms, color="lightgrey", label="other")
        ax.set_ylabel("% of characters")
        ax.set_title("What filled the context (largest sessions)")
        ax.legend(fontsize=7, loc="upper left", bbox_to_anchor=(1, 1))
        plt.setp(ax.get_xticklabels(), rotation=20, ha="right", fontsize=8)
        fig.tight_layout()
        p = out_dir / "composition.png"
        fig.savefig(p, dpi=130)
        plt.close(fig)
        made.append(p)
    return made
