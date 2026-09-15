"""Audit what a Claude Code installation loads into every session, what it costs, and what is used.

Sources, in order of authority:

* the configuration directory: skills, agents, instruction files, settings
* the plugin and MCP command-line tools, when available
* Claude Code's own usage counters in its state file
* the session transcripts: the listings actually sent, tool calls, hook timings

Output is a local report, a machine-readable inventory, and a plan of reversible changes.
Nothing here publishes anything; see docs/housekeeping.md for the rules and the apply/undo cycle.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .locate import config_dir, iter_sessions, projects_dir
from .redact import home_dir

CHARS_PER_TOKEN = 4
LISTING_CAP = 1536          # description text is truncated at this length in the skill listing
BIG_BODY_CHARS = 20_000     # a skill body above this is worth restructuring
LONG_INSTRUCTIONS_LINES = 200
SLOW_HOOK_MS_PER_SESSION = 1000
DEFAULT_WINDOW_DAYS = 90
BUILTIN_MCP = {"ide"}       # provided by the host integration, not something to deny


def canonical(name: str) -> str:
    """Tool names spell a server with underscores; listings and health use its display name."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

Runner = Callable[[list[str], int], "str | None"]


# --------------------------------------------------------------------------- helpers

def run_cmd(args: list[str], timeout: int = 60) -> str | None:
    """Run a command line tool and return stdout on success, None on any failure."""
    exe = shutil.which(args[0])
    if not exe:
        return None
    cmd = [exe] + args[1:]
    if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
        cmd = ["cmd", "/c"] + cmd
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def frontmatter(text: str) -> dict:
    """Minimal YAML front matter reader: scalar keys, plus folded or literal multi-line values."""
    m = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.S)
    if not m:
        return {}
    out: dict[str, str] = {}
    lines = m.group(1).splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        mm = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not mm:
            i += 1
            continue
        key, value = mm.group(1), mm.group(2).strip()
        if value in ("", ">", "|", ">-", "|-"):
            parts = []
            i += 1
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                parts.append(lines[i].strip())
                i += 1
            out[key] = " ".join(p for p in parts if p)
            continue
        out[key] = value.strip("\"'")
        i += 1
    return out


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("true", "yes", "1")


def _mtime_days(p: Path) -> int:
    return int((time.time() - p.stat().st_mtime) // 86400)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _load_json(p: Path) -> dict:
    try:
        return json.loads(_read(p))
    except (OSError, ValueError):
        return {}


def state_file(cfg: Path) -> Path:
    """Claude Code's application state file, beside the config directory."""
    candidate = cfg / ".claude.json"
    return candidate if candidate.is_file() else cfg.parent / ".claude.json"


# --------------------------------------------------------------------------- inventory

def skill_record(path: Path, source: str, listing_name: str) -> dict:
    text = _read(path)
    fm = frontmatter(text)
    desc = (fm.get("description", "") + " " + fm.get("when_to_use", "")).strip()
    body_chars = len(text)
    dmi = _truthy(fm.get("disable-model-invocation", "false"))
    return {
        "name": listing_name,
        "source": source,
        "path": str(path),
        "description_chars": len(desc),
        "listing_chars_estimate": 0 if dmi else min(len(desc), LISTING_CAP) + len(listing_name) + 4,
        "body_chars": body_chars,
        "on_invoke_tokens": body_chars // CHARS_PER_TOKEN,
        "model_invocable": not dmi,
        "modified_days_ago": _mtime_days(path),
    }


def inventory_skills(cfg: Path, project: Path | None, plugins: list[dict]) -> list[dict]:
    out: list[dict] = []
    for d in sorted((cfg / "skills").glob("*/SKILL.md")):
        out.append(skill_record(d, "user", d.parent.name))
    for f in sorted((cfg / "commands").rglob("*.md")):
        out.append(skill_record(f, "user command", f.stem))
    if project:
        for d in sorted((project / ".claude" / "skills").glob("*/SKILL.md")):
            out.append(skill_record(d, "project", d.parent.name))
        for f in sorted((project / ".claude" / "commands").rglob("*.md")):
            out.append(skill_record(f, "project command", f.stem))
    for pl in plugins:
        if not pl.get("enabled"):
            continue
        root = Path(pl.get("installPath") or "")
        short = pl["id"].split("@")[0]
        for d in sorted(root.glob("skills/*/SKILL.md")):
            out.append(skill_record(d, f"plugin:{pl['id']}", f"{short}:{d.parent.name}"))
        for f in sorted(root.glob("commands/*.md")):
            out.append(skill_record(f, f"plugin:{pl['id']}", f"{short}:{f.stem}"))
    return out


def inventory_agents(cfg: Path, project: Path | None) -> list[dict]:
    out = []
    dirs = [(cfg / "agents", "user")] + ([(project / ".claude" / "agents", "project")] if project else [])
    for d, source in dirs:
        for f in sorted(d.glob("*.md")):
            fm = frontmatter(_read(f))
            out.append({"name": f.stem, "source": source, "path": str(f),
                        "listing_chars_estimate": len(f.stem) + len(fm.get("description", "")) + 4,
                        "body_chars": f.stat().st_size, "modified_days_ago": _mtime_days(f)})
    return out


def inventory_instructions(cfg: Path, project: Path | None) -> list[dict]:
    out = []
    candidates = [(cfg / "CLAUDE.md", "user")]
    candidates += [(p, "user rule") for p in sorted((cfg / "rules").glob("**/*.md"))]
    if project:
        candidates += [(project / "CLAUDE.md", "project"), (project / ".claude" / "CLAUDE.md", "project"),
                       (project / "CLAUDE.local.md", "project local")]
        candidates += [(p, "project rule") for p in sorted((project / ".claude" / "rules").glob("**/*.md"))]
    for p, scope in candidates:
        if p.is_file():
            text = _read(p)
            out.append({"path": str(p), "scope": scope, "chars": len(text), "lines": len(text.splitlines())})
    return out


def inventory_settings(cfg: Path) -> dict:
    s = _load_json(cfg / "settings.json")
    hooks = []
    for event, groups in (s.get("hooks") or {}).items():
        for g in groups if isinstance(groups, list) else []:
            for h in g.get("hooks", []) if isinstance(g, dict) else []:
                hooks.append({"event": event, "matcher": g.get("matcher", "*"),
                              "command": h.get("command") or h.get("type")})
    return {
        "hooks": hooks,
        "enabledPlugins": s.get("enabledPlugins") or {},
        "skillOverrides": s.get("skillOverrides") or {},
        "deniedMcpServers": s.get("deniedMcpServers") or [],
        "disableClaudeAiConnectors": bool(s.get("disableClaudeAiConnectors")),
        "cleanupPeriodDays": s.get("cleanupPeriodDays"),
        "autoMemoryEnabled": s.get("autoMemoryEnabled"),
        "effortLevel": s.get("effortLevel"),
        "model": s.get("model"),
    }


def inventory_plugins(cfg: Path, run: Runner) -> list[dict]:
    """Installed plugins from the command line tool, else from the plugin registry on disk."""
    out = run(["claude", "plugin", "list", "--json"], 60)
    plugins: list[dict] = []
    if out:
        try:
            plugins = [p for p in json.loads(out) if isinstance(p, dict)]
        except ValueError:
            plugins = []
    if not plugins:
        reg = _load_json(cfg / "plugins" / "installed_plugins.json")
        entries = reg.get("plugins", reg) if isinstance(reg, dict) else {}
        enabled = (_load_json(cfg / "settings.json").get("enabledPlugins") or {})
        for pid, v in (entries.items() if isinstance(entries, dict) else []):
            for e in (v if isinstance(v, list) else [v]):
                if isinstance(e, dict):
                    plugins.append({"id": pid, "version": e.get("version"), "scope": e.get("scope"),
                                    "enabled": bool(enabled.get(pid)), "installPath": e.get("installPath"),
                                    "installedAt": e.get("installedAt"), "lastUpdated": e.get("lastUpdated")})
    for p in plugins:
        root = Path(p.get("installPath") or "")
        manifest = _load_json(root / ".claude-plugin" / "plugin.json") if root.is_dir() else {}
        p["has_lsp"] = (root / ".lsp.json").is_file() or bool(manifest.get("lspServers")) \
            or any(root.glob("*.lsp.json")) or "lsp" in p["id"].split("@")[0].lower()
        p["has_mcp"] = (root / ".mcp.json").is_file() or bool(manifest.get("mcpServers"))
        p["cached_versions"] = len(list(root.parent.iterdir())) if root.parent.is_dir() else 0
        p["always_on_tokens"] = None
        if p.get("enabled"):
            details = run(["claude", "plugin", "details", p["id"]], 60) or ""
            m = re.search(r"Always-on:\s*~?([\d,.]+)\s*(k?)\s*tok", details)
            if m:
                n = float(m.group(1).replace(",", ""))
                p["always_on_tokens"] = int(n * (1000 if m.group(2) == "k" else 1))
    return plugins


def mcp_health(run: Runner) -> dict[str, str]:
    """Server name -> status text, from the MCP command line tool. Empty when unavailable."""
    out = run(["claude", "mcp", "list"], 90) or ""
    health: dict[str, str] = {}
    for line in out.splitlines():
        m = re.match(r"^(.*?):\s+\S+\s+-\s+(.*)$", line.strip())
        if m:
            health[m.group(1).strip()] = m.group(2).strip()
    return health


def state_usage(cfg: Path) -> dict:
    """Claude Code's own counters: skills, plugins and tools with usage count and last-used time."""
    st = _load_json(state_file(cfg))

    def conv(d):
        out = {}
        for k, v in (d or {}).items():
            if isinstance(v, dict):
                ts = v.get("lastUsedAt")
                out[k] = {"count": int(v.get("usageCount") or 0),
                          "last": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat() if ts else None}
        return out

    tools = conv(st.get("toolUsage"))
    servers: dict[str, dict] = {}
    for name, v in tools.items():
        if name.startswith("mcp__"):
            srv = name.split("__")[1]
            cur = servers.setdefault(srv, {"count": 0, "last": None})
            cur["count"] += v["count"]
            cur["last"] = max(cur["last"] or "", v["last"] or "") or None
    return {"skills": conv(st.get("skillUsage")), "plugins": conv(st.get("pluginUsage")),
            "mcp_servers": servers}


# --------------------------------------------------------------------------- transcripts

def transcript_usage(projects: Path | None, since: datetime) -> dict:
    """Tool calls, listings and hook timings from every transcript on disk."""
    since_s = since.date().isoformat()
    use = {"skills": defaultdict(lambda: {"count": 0, "sessions": set(), "last": None}),
           "agents": defaultdict(lambda: {"count": 0, "sessions": set(), "last": None}),
           "mcp_servers": defaultdict(lambda: {"count": 0, "sessions": set(), "last": None}),
           "commands": defaultdict(lambda: {"count": 0, "sessions": set(), "last": None})}
    hooks: dict[str, dict] = defaultdict(lambda: {"fires": 0, "ms": 0, "sessions": set()})
    listing = {"skills": {}, "agents": {}, "mcp": {}, "mcp_tools": Counter(), "session_mtime": 0.0}
    sessions_in_window = 0

    def bump(bucket, key, sid, ts):
        r = use[bucket][key]
        if ts >= since_s:
            r["count"] += 1
            r["sessions"].add(sid)
        r["last"] = max(r["last"] or "", ts) or None

    for ref in iter_sessions(projects):
        files = [ref.path] + list(ref.subagent_paths)
        sid = ref.session_id
        try:
            mtime = ref.path.stat().st_mtime
        except OSError:
            mtime = 0.0
        take_listing = mtime > listing["session_mtime"]
        counted = False
        for f in files:
            try:
                fh = f.open(encoding="utf-8", errors="replace")
            except OSError:
                continue
            with fh:
                for line in fh:
                    if '"tool_use"' not in line and '"attachment"' not in line and "<command-name>" not in line:
                        continue
                    try:
                        o = json.loads(line)
                    except ValueError:
                        continue
                    ts = (o.get("timestamp") or "")[:10]
                    if ts >= since_s and not counted:
                        sessions_in_window += 1
                        counted = True
                    t = o.get("type")
                    if t == "assistant":
                        for b in (o.get("message") or {}).get("content") or []:
                            if not isinstance(b, dict) or b.get("type") != "tool_use":
                                continue
                            n = b.get("name", "")
                            inp = b.get("input") or {}
                            if n == "Skill":
                                bump("skills", str(inp.get("skill", "?")), sid, ts)
                            elif n == "Agent":
                                bump("agents", str(inp.get("subagent_type") or "general-purpose"), sid, ts)
                            elif n.startswith("mcp__"):
                                bump("mcp_servers", n.split("__")[1], sid, ts)
                    elif t == "user":
                        c = (o.get("message") or {}).get("content")
                        if isinstance(c, str) and "<command-name>" in c:
                            m = re.search(r"<command-name>(.*?)</command-name>", c)
                            if m:
                                bump("commands", m.group(1).strip(), sid, ts)
                    elif t == "attachment":
                        a = o.get("attachment") or {}
                        kind = a.get("type")
                        if kind == "hook_success" and ts >= since_s:
                            key = f"{a.get('hookName', '?')} :: {a.get('command', '')}"
                            hooks[key]["fires"] += 1
                            hooks[key]["ms"] += int(a.get("durationMs") or 0)
                            hooks[key]["sessions"].add(sid)
                        elif take_listing and f == ref.path:
                            if kind == "skill_listing" and a.get("content"):
                                entries = {}
                                for mm in re.finditer(r"^- (\S+?): (.*)$", a["content"], re.M):
                                    entries[mm.group(1)] = len(mm.group(0))
                                if entries:
                                    listing["skills"] = entries
                                    listing["session_mtime"] = mtime
                            elif kind == "agent_listing_delta":
                                for ln in a.get("addedLines") or []:
                                    mm = re.match(r"^- (\S+?): ", ln)
                                    if mm:
                                        listing["agents"][mm.group(1)] = len(ln)
                            elif kind == "mcp_instructions_delta":
                                for name, block in zip(a.get("addedNames") or [], a.get("addedBlocks") or []):
                                    listing["mcp"][name] = len(block)
                            elif kind == "deferred_tools_delta":
                                for name in a.get("addedNames") or []:
                                    if name.startswith("mcp__"):
                                        listing["mcp_tools"][name.split("__")[1]] += 1

    def freeze(d):
        return {k: {"count": v["count"], "sessions": len(v["sessions"]), "last": v["last"]} for k, v in d.items()}

    return {
        "since": since_s,
        "sessions_in_window": sessions_in_window,
        "skills": freeze(use["skills"]),
        "agents": freeze(use["agents"]),
        "mcp_servers": freeze(use["mcp_servers"]),
        "commands": freeze(use["commands"]),
        "hooks": {k: {"fires": v["fires"], "ms": v["ms"], "sessions": len(v["sessions"])} for k, v in hooks.items()},
        "listing": {"skills": listing["skills"], "agents": listing["agents"], "mcp": listing["mcp"],
                    "mcp_tools": dict(listing["mcp_tools"])},
    }


# --------------------------------------------------------------------------- assessment

def _used(count_in_window: int, state: dict | None, since_s: str) -> bool:
    if count_in_window:
        return True
    return bool(state and state.get("last") and state["last"] >= since_s)


def assess(inv: dict, usage: dict, state: dict, window_days: int) -> dict:
    """Apply the housekeeping rules. Returns findings split into reversible actions and notes."""
    since_s = usage["since"]
    actions: list[dict] = []
    notes: list[dict] = []
    listing = usage["listing"]
    overrides = inv["settings"]["skillOverrides"]
    denied = set(inv["settings"]["deniedMcpServers"])

    known = {s["name"] for s in inv["skills"]}
    for name, chars in listing["skills"].items():
        if name not in known:
            inv["skills"].append({"name": name, "source": "bundled", "path": None, "description_chars": None,
                                  "listing_chars_estimate": chars, "body_chars": None, "on_invoke_tokens": None,
                                  "model_invocable": True, "modified_days_ago": None})

    for s in inv["skills"]:
        measured = listing["skills"].get(s["name"])
        s["listing_chars"] = measured if measured is not None else s["listing_chars_estimate"]
        s["listed"] = s["name"] in listing["skills"] if listing["skills"] else s["model_invocable"]
        tu = usage["skills"].get(s["name"], {})
        typed = usage["commands"].get("/" + s["name"], {})  # invoked by the user as a slash command
        su = state["skills"].get(s["name"])
        s["uses_in_window"] = tu.get("count", 0) + typed.get("count", 0)
        s["sessions_in_window"] = tu.get("sessions", 0) + typed.get("sessions", 0)
        s["last_used"] = max(tu.get("last") or "", typed.get("last") or "", (su or {}).get("last") or "") or None
        s["all_time_count"] = (su or {}).get("count")
        s["override"] = overrides.get(s["name"], "on")
        used = _used(s["uses_in_window"], su, since_s)
        if s["body_chars"] and s["body_chars"] > BIG_BODY_CHARS:
            notes.append({"kind": "skill", "item": s["name"],
                          "note": f"body is {s['body_chars']:,} chars (~{s['on_invoke_tokens']:,} tokens on every "
                                  f"invocation); restructure into a short SKILL.md plus files read on demand"})
        if s["listed"] and not used and s["override"] == "on":
            if s["source"].startswith("plugin:"):
                continue  # plugin skills are governed by the plugin; handled below
            actions.append({"op": "skill_override", "skill": s["name"], "value": "user-invocable-only",
                            "saves_chars_per_session": s["listing_chars"],
                            "why": f"listed to the model every session, not used in {window_days} days"})

    for p in inv["plugins"]:
        if not p.get("enabled"):
            continue
        pid = p["id"]
        short = pid.split("@")[0]
        p_skills = [s for s in inv["skills"] if s["source"] == f"plugin:{pid}"]
        used_skills = [s for s in p_skills if _used(s["uses_in_window"], state["skills"].get(s["name"]), since_s)]
        st = state["plugins"].get(pid)
        p["skills_total"], p["skills_used"] = len(p_skills), len(used_skills)
        p["last_used"] = (st or {}).get("last")
        if p.get("has_lsp"):
            notes.append({"kind": "plugin", "item": pid, "note": "language server plugin; usage is not visible "
                          "in transcripts, left alone"})
        elif not used_skills and not _used(0, st, since_s):
            actions.append({"op": "plugin_disable", "plugin": pid,
                            "saves_tokens_per_session": p.get("always_on_tokens"),
                            "why": f"enabled, none of its {len(p_skills)} skills used in {window_days} days"})
        elif p_skills and len(used_skills) < len(p_skills):
            unused = ", ".join(s["name"].split(":", 1)[1] for s in p_skills if s not in used_skills)
            notes.append({"kind": "plugin", "item": pid,
                          "note": f"{len(used_skills)} of {len(p_skills)} skills used; plugin skills cannot be "
                                  f"hidden one by one, so the unused ones ({unused}) stay listed while the plugin is on"})
        if p.get("cached_versions", 0) > 2:
            notes.append({"kind": "plugin", "item": pid,
                          "note": f"{p['cached_versions']} versions cached on disk; only the installed one loads"})

    for a in inv["agents"]:
        tu = usage["agents"].get(a["name"], {})
        a["uses_in_window"] = tu.get("count", 0)
        a["last_used"] = tu.get("last")
        a["listing_chars"] = listing["agents"].get(a["name"], a["listing_chars_estimate"])
        if not a["uses_in_window"]:
            actions.append({"op": "archive_file", "path": a["path"], "kind": "agent", "item": a["name"],
                            "saves_chars_per_session": a["listing_chars"],
                            "why": f"custom agent listed every session, not delegated to in {window_days} days"})

    # Merge every spelling of a server under one record, preferring the display name.
    servers: dict[str, dict] = {}

    def rec_for(name: str) -> dict:
        r = servers.setdefault(canonical(name), {"name": name})
        if " " in name or "." in name:
            r["name"] = name
        return r

    for name, chars in listing["mcp"].items():
        rec_for(name)["instruction_chars"] = chars
    for name, n in listing["mcp_tools"].items():
        rec_for(name)["tools"] = n
    for name, health in inv["mcp_health"].items():
        rec_for(name)["health"] = health
    for name in set(usage["mcp_servers"]) | set(state["mcp_servers"]):
        rec_for(name)
    inv["mcp_servers"] = []
    for key, rec in sorted(servers.items()):
        tu = next((v for k, v in usage["mcp_servers"].items() if canonical(k) == key), {})
        su = next((v for k, v in state["mcp_servers"].items() if canonical(k) == key), None)
        name = rec["name"]
        rec.update({"calls_in_window": tu.get("count", 0), "sessions_in_window": tu.get("sessions", 0),
                    "last_used": max(tu.get("last") or "", (su or {}).get("last") or "") or None,
                    "denied": any(canonical(d) == key for d in denied), "builtin": key in BUILTIN_MCP})
        inv["mcp_servers"].append(rec)
        if "health" in rec and "connected" not in rec["health"].lower():
            notes.append({"kind": "mcp", "item": name, "note": f"health: {rec['health']}"})
        if rec["builtin"] or rec["denied"]:
            continue
        if not _used(rec["calls_in_window"], su, since_s) and (rec.get("tools") or rec.get("instruction_chars") or rec.get("health")):
            actions.append({"op": "deny_mcp", "server": name,
                            "saves_chars_per_session": rec.get("instruction_chars", 0),
                            "why": f"connected every session, no tool call in {window_days} days"})

    inv["hooks"] = []
    for key, h in sorted(usage["hooks"].items(), key=lambda kv: -kv[1]["ms"]):
        active = max(h["sessions"], 1)
        rec = {"hook": key, "fires": h["fires"], "total_ms": h["ms"], "sessions": h["sessions"],
               "ms_per_active_session": round(h["ms"] / active, 1)}
        inv["hooks"].append(rec)
        if rec["ms_per_active_session"] > SLOW_HOOK_MS_PER_SESSION:
            notes.append({"kind": "hook", "item": key,
                          "note": f"{rec['ms_per_active_session']:,} ms per session in which it fired"})

    for f in inv["instructions"]:
        if f["lines"] > LONG_INSTRUCTIONS_LINES:
            notes.append({"kind": "instructions", "item": f["path"],
                          "note": f"{f['lines']} lines; the documentation suggests staying under {LONG_INSTRUCTIONS_LINES}"})
    if inv["settings"]["cleanupPeriodDays"] is None:
        notes.append({"kind": "settings", "item": "cleanupPeriodDays",
                      "note": "not set; transcripts are deleted after 30 days by default"})

    return {"actions": actions, "notes": notes}


# --------------------------------------------------------------------------- report

def _fmt(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.1f}"
    return str(v)


def _table(rows: list[dict], cols: list[str], headers: list[str] | None = None) -> str:
    if not rows:
        return "_none_\n"
    heads = headers or cols
    lines = ["| " + " | ".join(heads) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(_fmt(r.get(c)) for c in cols) + " |")
    return "\n".join(lines) + "\n"


def write_report(out_dir: Path, inv: dict, usage: dict, findings: dict, window_days: int) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    listing = usage["listing"]
    by_source: Counter = Counter()
    for s in inv["skills"]:
        if s.get("listed"):
            by_source[s["source"].split(":")[0]] += s["listing_chars"]
    total_listing = sum(by_source.values())
    saves_chars = sum(a.get("saves_chars_per_session") or 0 for a in findings["actions"])
    saves_tokens = sum(a.get("saves_tokens_per_session") or 0 for a in findings["actions"])
    skills = sorted(inv["skills"], key=lambda s: (-(s.get("listing_chars") or 0), s["name"]))
    lines = [
        "# Housekeeping audit",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. Usage window: {window_days} days "
        f"({usage['sessions_in_window']} sessions). This report describes one machine's setup and stays local.",
        "",
        "## Startup cost from the latest session's listings",
        "",
        _table([{"source": k, "chars": v, "tokens": v // CHARS_PER_TOKEN} for k, v in by_source.most_common()]
               + [{"source": "agents", "chars": sum(listing["agents"].values()), "tokens": sum(listing["agents"].values()) // CHARS_PER_TOKEN},
                  {"source": "mcp instructions", "chars": sum(listing["mcp"].values()), "tokens": sum(listing["mcp"].values()) // CHARS_PER_TOKEN}],
               ["source", "chars", "tokens"]),
        f"Skill listing total: {total_listing:,} chars (~{total_listing // CHARS_PER_TOKEN:,} tokens), re-sent after every compaction. "
        f"Proposed actions would remove about {saves_chars // CHARS_PER_TOKEN + saves_tokens:,} tokens per session.",
        "",
        "## Skills",
        "",
        _table(skills, ["name", "source", "listed", "override", "listing_chars", "on_invoke_tokens", "uses_in_window",
                        "sessions_in_window", "last_used", "modified_days_ago"],
               ["skill", "source", "listed", "override", "listing chars", "tokens on invoke", "uses", "sessions",
                "last used", "modified (days)"]),
        "## Plugins",
        "",
        _table(inv["plugins"], ["id", "version", "scope", "enabled", "always_on_tokens", "skills_used", "skills_total",
                                "last_used", "has_lsp", "cached_versions"],
               ["plugin", "version", "scope", "enabled", "always-on tokens", "skills used", "skills", "last used",
                "lsp", "cached versions"]),
        "## Custom agents",
        "",
        _table(inv["agents"], ["name", "source", "listing_chars", "uses_in_window", "last_used", "modified_days_ago"],
               ["agent", "source", "listing chars", "uses", "last used", "modified (days)"]),
        "## MCP servers and connectors",
        "",
        _table(inv["mcp_servers"], ["name", "tools", "instruction_chars", "calls_in_window", "sessions_in_window",
                                    "last_used", "health", "denied", "builtin"],
               ["server", "tools", "instruction chars", "calls", "sessions", "last used", "health", "denied", "built in"]),
        "## Hooks (as recorded in transcripts)",
        "",
        _table(inv["hooks"], ["hook", "fires", "sessions", "total_ms", "ms_per_active_session"],
               ["hook", "fires", "sessions", "total ms", "ms per session where it fired"]),
        "## Instruction files",
        "",
        _table(inv["instructions"], ["path", "scope", "lines", "chars"]),
        "## Notes (need a judgement, not applied automatically)",
        "",
        "\n".join(f"- **{n['kind']}** {n['item']}: {n['note']}" for n in findings["notes"]) or "_none_",
        "",
        "## Proposed reversible actions",
        "",
        "\n".join(f"- `{a['op']}` {a.get('skill') or a.get('plugin') or a.get('server') or a.get('item')}: {a['why']}"
                  for a in findings["actions"]) or "_none_",
        "",
        f"Review and edit `plan.json`, then apply with `ctxeng audit --apply {out_dir / 'plan.json'}`. "
        "Every applied change can be reversed with `ctxeng audit --undo`.",
    ]
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "inventory.json").write_text(json.dumps({"inventory": inv, "usage": usage}, indent=2, default=str),
                                            encoding="utf-8")
    (out_dir / "plan.json").write_text(json.dumps({"generated": datetime.now(timezone.utc).isoformat(),
                                                   "actions": findings["actions"], "notes": findings["notes"]},
                                                  indent=2), encoding="utf-8")
    return out_dir / "report.md"


# --------------------------------------------------------------------------- orchestration

def run_audit(out_dir: Path, *, window_days: int = DEFAULT_WINDOW_DAYS, project: Path | None = None,
              cfg: Path | None = None, projects: Path | None = None, network: bool = True,
              run: Runner = run_cmd) -> Path:
    cfg = cfg or config_dir()
    quiet: Runner = (lambda args, timeout: None)
    runner = run if network else quiet
    plugins = inventory_plugins(cfg, runner)
    inv = {
        "config_dir": str(cfg),
        "skills": inventory_skills(cfg, project, plugins),
        "agents": inventory_agents(cfg, project),
        "instructions": inventory_instructions(cfg, project),
        "settings": inventory_settings(cfg),
        "plugins": plugins,
        "mcp_health": mcp_health(runner),
    }
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    usage = transcript_usage(projects or projects_dir(cfg), since)
    state = state_usage(cfg)
    findings = assess(inv, usage, state, window_days)
    return write_report(out_dir, inv, usage, findings, window_days)


# --------------------------------------------------------------------------- apply / undo

def apply_plan(plan_path: Path, *, cfg: Path | None = None, run: Runner = run_cmd) -> Path:
    """Apply the reversible actions in a plan. Writes an undo record and returns its path."""
    cfg = cfg or config_dir()
    plan = _load_json(plan_path)
    actions = plan.get("actions") or []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    undo_dir = home_dir() / "housekeeping" / stamp
    undo_dir.mkdir(parents=True, exist_ok=True)
    settings_path = cfg / "settings.json"
    settings = _load_json(settings_path)
    backup = undo_dir / "settings.before.json"
    if settings_path.is_file():
        shutil.copy2(settings_path, backup)
    record = {"applied": [], "settings_backup": str(backup) if settings_path.is_file() else None,
              "settings_path": str(settings_path)}
    changed_settings = False
    for a in actions:
        op = a.get("op")
        if op == "skill_override":
            settings.setdefault("skillOverrides", {})[a["skill"]] = a.get("value", "user-invocable-only")
            changed_settings = True
            record["applied"].append(a)
        elif op == "deny_mcp":
            lst = settings.setdefault("deniedMcpServers", [])
            if a["server"] not in lst:
                lst.append(a["server"])
            changed_settings = True
            record["applied"].append(a)
        elif op == "plugin_disable":
            if run(["claude", "plugin", "disable", a["plugin"]], 60) is not None:
                record["applied"].append(a)
        elif op == "archive_file":
            src = Path(a["path"])
            if src.is_file():
                dest = undo_dir / "archive" / src.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))
                record["applied"].append({**a, "archived_to": str(dest)})
    if changed_settings:
        settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    undo_path = undo_dir / "applied.json"
    undo_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return undo_path


def undo(applied_path: Path, *, run: Runner = run_cmd) -> int:
    """Reverse an applied plan: restore the settings file, move archived files back, re-enable plugins."""
    rec = _load_json(applied_path)
    n = 0
    if rec.get("settings_backup") and Path(rec["settings_backup"]).is_file():
        shutil.copy2(rec["settings_backup"], rec["settings_path"])
        n += 1
    for a in rec.get("applied", []):
        if a.get("op") == "archive_file" and a.get("archived_to") and Path(a["archived_to"]).is_file():
            Path(a["path"]).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(a["archived_to"], a["path"])
            n += 1
        elif a.get("op") == "plugin_disable":
            if run(["claude", "plugin", "enable", a["plugin"]], 60) is not None:
                n += 1
    return n
