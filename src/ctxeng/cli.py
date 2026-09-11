"""Command-line entry point. Output uses pseudonyms unless ``--raw`` is given."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import metrics
from .locate import find_sessions, iter_sessions, projects_dir
from .parse import parse_session
from .redact import project_alias, session_alias


def _ident(raw: bool):
    if raw:
        return (lambda p: p), (lambda s: s)
    return project_alias, session_alias


def print_table(rows: list[dict], columns: list[str] | None = None, file=None) -> None:
    file = file or sys.stdout
    if not rows:
        print("(no data)", file=file)
        return
    cols = columns or list(rows[0].keys())
    cells = [[_cell(r.get(c)) for c in cols] for r in rows]
    widths = [max(len(c), *(len(row[i]) for row in cells)) for i, c in enumerate(cols)]
    print("  ".join(c.ljust(w) for c, w in zip(cols, widths)), file=file)
    print("  ".join("-" * w for w in widths), file=file)
    for row in cells:
        print("  ".join(v.rjust(w) if _numeric(v) else v.ljust(w) for v, w in zip(row, widths)), file=file)


def _cell(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "yes" if v else ""
    if isinstance(v, float):
        return f"{v:,.1f}" if abs(v) < 100 else f"{v:,.0f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def _numeric(s: str) -> bool:
    return s.replace(",", "").replace(".", "").replace("-", "").isdigit()


def _load(args, min_calls: int = 0):
    refs = list(iter_sessions(args.projects, getattr(args, "project", None)))
    sessions = [parse_session(r) for r in refs]
    return [s for s in sessions if len(s.api_calls) >= min_calls]


def _one(args):
    matches = find_sessions(args.session, args.projects)
    if not matches:
        sys.exit(f"no session id starts with {args.session!r}")
    if len(matches) > 1:
        sys.exit("ambiguous prefix; matches: " + ", ".join(m.session_id[:12] for m in matches))
    return parse_session(matches[0])


def cmd_scan(args) -> None:
    pa, sa = _ident(args.raw)
    rows = []
    for s in _load(args, args.min_calls):
        r = metrics.session_summary(s)
        r["project"], r["session"] = pa(r["project"]), sa(r["session"])
        rows.append(r)
    rows.sort(key=lambda r: r["date"])
    print_table(rows, ["date", "project", "session", "model", "effort", "version", "prompts",
                       "api_calls", "tool_calls", "peak_context", "compactions", "subagents"])
    print(f"\n{len(rows)} sessions from {args.projects or projects_dir()}")


def cmd_session(args) -> None:
    s = _one(args)
    pa, sa = _ident(args.raw)
    summary = metrics.session_summary(s)
    summary["project"], summary["session"] = pa(summary["project"]), sa(summary["session"])
    width = max(len(k) for k in summary)
    for k, v in summary.items():
        print(f"{k.ljust(width)}  {_cell(v)}")
    if s.compactions:
        print("\ncompactions:")
        print_table(metrics.compaction_rows(s), ["trigger", "prompt_index", "api_call_index", "pre_tokens",
                                                  "post_tokens", "retained_pct", "summary_chars"])
    drops = metrics.context_drops(s)
    if drops:
        print("\ncontext drops without a compaction:")
        print_table(drops, ["call", "prompt_index", "model_before", "model_after", "before", "after",
                            "dropped", "dropped_pct"])


def cmd_prompts(args) -> None:
    s = _one(args)
    print_table(metrics.prompt_costs(s), ["prompt_index", "kind", "model", "effort", "api_calls", "tool_calls",
                                          "tool_result_chars", "context_start", "context_end", "added_tokens",
                                          "output_tokens", "duration_s", "compaction"])


def cmd_composition(args) -> None:
    s = _one(args)
    rows = [{**r, "share_pct": round(100 * r["share"], 1)} for r in metrics.composition(s)]
    print_table(rows, ["source", "chars", "est_tokens", "share_pct"])


def cmd_compactions(args) -> None:
    pa, sa = _ident(args.raw)
    rows = []
    for s in _load(args):
        for r in metrics.compaction_rows(s):
            r["project"], r["session"] = pa(r["project"]), sa(r["session"])
            rows.append(r)
    rows.sort(key=lambda r: r["timestamp"])
    print_table(rows, ["timestamp", "project", "session", "model", "trigger", "pre_tokens", "post_tokens",
                       "retained_pct", "duration_s", "summary_chars", "calls_after", "prompts_after"])


def cmd_growth(args) -> None:
    rows = [r for s in _load(args, args.min_calls) for r in metrics.prompt_costs(s)]
    agg = metrics.aggregate_prompt_costs(rows, args.by)
    print_table(agg, ["group", "sessions", "prompts", "added_tokens_median", "added_tokens_p90",
                      "api_calls_median", "api_calls_p90", "tool_calls_median",
                      "tool_result_chars_median", "output_tokens_median"])


def cmd_baseline(args) -> None:
    print_table(metrics.baseline_by(_load(args, 1), args.by), ["group", "n", "median", "p90", "mean"])


def cmd_report(args) -> None:
    from .report import build_report
    path = build_report(_load(args), Path(args.out), charts=args.charts, top=args.top,
                        min_calls=args.min_calls)
    print(f"wrote {path}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ctxeng", description=__doc__)
    ap.add_argument("--projects", type=Path, default=None,
                    help="transcript root (default: Claude Code's projects directory)")
    sub = ap.add_subparsers(dest="command", required=True)

    def common(p, project=True, raw=True, min_calls=None):
        if project:
            p.add_argument("--project", help="only projects whose slug contains this text")
        if raw:
            p.add_argument("--raw", action="store_true", help="show real identifiers (local use only)")
        if min_calls is not None:
            p.add_argument("--min-calls", type=int, default=min_calls,
                           help=f"skip sessions with fewer API calls (default {min_calls})")

    p = sub.add_parser("scan", help="list sessions")
    common(p, min_calls=1)
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("session", help="summarise one session")
    p.add_argument("session", help="session id prefix")
    common(p, project=False)
    p.set_defaults(fn=cmd_session)

    p = sub.add_parser("prompts", help="per-prompt context cost for one session")
    p.add_argument("session")
    common(p, project=False, raw=False)
    p.set_defaults(fn=cmd_prompts)

    p = sub.add_parser("composition", help="what filled one session's context")
    p.add_argument("session")
    common(p, project=False, raw=False)
    p.set_defaults(fn=cmd_composition)

    p = sub.add_parser("compactions", help="every compaction event")
    common(p)
    p.set_defaults(fn=cmd_compactions)

    p = sub.add_parser("growth", help="context growth per prompt, aggregated")
    p.add_argument("--by", choices=["model", "effort", "version", "kind"], default="model")
    common(p, raw=False, min_calls=5)
    p.set_defaults(fn=cmd_growth)

    p = sub.add_parser("baseline", help="context already present on the first call")
    p.add_argument("--by", choices=["version", "model", "effort"], default="version")
    common(p, raw=False)
    p.set_defaults(fn=cmd_baseline)

    p = sub.add_parser("report", help="write CSVs, a Markdown report and optional charts")
    p.add_argument("--out", default="out")
    p.add_argument("--charts", action="store_true")
    p.add_argument("--top", type=int, default=6, help="sessions to detail")
    common(p, raw=False, min_calls=5)
    p.set_defaults(fn=cmd_report)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.fn(args)
    return 0
