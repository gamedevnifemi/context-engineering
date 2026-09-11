#!/usr/bin/env python3
"""Scan content that is about to be committed for personal or raw-transcript material.

Two layers of protection:

1. Built-in patterns that are personal on any machine: email addresses, home-directory paths,
   Claude Code project slugs derived from home paths, and common credential formats. These live
   in ``ctxeng.patterns`` so the scanner and the report redaction share one definition.
2. A denylist of terms specific to the maintainer, read from a file that lives OUTSIDE the
   repository (``CTXENG_DENYLIST`` env var, else ``~/.ctxeng/denylist.txt``). Because that file is
   never committed, the terms it protects never appear in the repo either.

Usage:
  privacy_check.py --staged            scan staged files (pre-commit hook)
  privacy_check.py --message FILE      scan a commit message (commit-msg hook)
  privacy_check.py PATH [PATH ...]     scan files or directories on demand
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ctxeng.patterns import find_personal  # noqa: E402

# Paths that must never be committed regardless of content.
FORBIDDEN_PATH_RULES = (
    (re.compile(r"\.jsonl$"), "raw transcript file"),
    (re.compile(r"(^|/)out/"), "generated output directory"),
    (re.compile(r"(^|/)\.ctxeng/"), "local ctxeng configuration"),
    (re.compile(r"denylist", re.I), "privacy denylist"),
)

SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".woff", ".woff2", ".zip"}


def denylist_path() -> Path:
    env = os.environ.get("CTXENG_DENYLIST")
    if env:
        return Path(env).expanduser()
    home = Path(os.environ.get("CTXENG_HOME", "~/.ctxeng")).expanduser()
    return home / "denylist.txt"


def load_denylist() -> list[re.Pattern[str]]:
    path = denylist_path()
    if not path.is_file():
        return []
    patterns: list[re.Pattern[str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        term = raw.strip()
        if not term or term.startswith("#"):
            continue
        # Word boundaries for plain words keep short names from matching inside unrelated words.
        if re.fullmatch(r"[\w.+-]+", term):
            patterns.append(re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.I))
        else:
            patterns.append(re.compile(re.escape(term), re.I))
    return patterns


def scan_text(text: str, denylist: list[re.Pattern[str]]) -> list[tuple[int, str, str]]:
    """Return (line_number, kind, snippet) for every hit in ``text``."""
    hits: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for kind, match in find_personal(line):
            hits.append((lineno, kind, match))
        for pat in denylist:
            m = pat.search(line)
            if m:
                hits.append((lineno, "denylisted term", m.group(0)))
    return hits


def staged_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
        check=True, capture_output=True,
    ).stdout.decode("utf-8", "replace")
    return [p for p in out.split("\0") if p]


def staged_content(path: str) -> bytes:
    return subprocess.run(["git", "show", f":{path}"], check=True, capture_output=True).stdout


def check_blobs(items: list[tuple[str, bytes]], denylist: list[re.Pattern[str]]) -> int:
    problems = 0
    for rel, data in items:
        for rule, why in FORBIDDEN_PATH_RULES:
            if rule.search(rel.replace("\\", "/")):
                print(f"{rel}: forbidden path ({why})")
                problems += 1
        if Path(rel).suffix.lower() in SKIP_SUFFIXES or b"\0" in data[:8000]:
            continue  # binary content cannot be scanned as text
        for lineno, kind, snippet in scan_text(data.decode("utf-8", "replace"), denylist):
            print(f"{rel}:{lineno}: {kind}: {snippet}")
            problems += 1
    return problems


def gather_paths(paths: list[str]) -> list[tuple[str, bytes]]:
    items: list[tuple[str, bytes]] = []
    for p in paths:
        path = Path(p)
        files = [f for f in path.rglob("*") if f.is_file()] if path.is_dir() else [path]
        for f in files:
            if any(part in {".git", "__pycache__", ".venv", "out"} for part in f.parts):
                continue
            try:
                rel = str(f.resolve().relative_to(ROOT))
            except ValueError:
                rel = str(f)
            items.append((rel, f.read_bytes()))
    return items


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--staged", action="store_true", help="scan the files staged for commit")
    ap.add_argument("--message", metavar="FILE", help="scan a commit message file")
    ap.add_argument("paths", nargs="*", help="files or directories to scan")
    args = ap.parse_args(argv)

    denylist = load_denylist()
    if not denylist:
        print(f"privacy_check: note: no denylist found at {denylist_path()}; built-in patterns only",
              file=sys.stderr)

    problems = 0
    if args.staged:
        problems += check_blobs([(p, staged_content(p)) for p in staged_files()], denylist)
    if args.message:
        text = Path(args.message).read_text(encoding="utf-8", errors="replace")
        for lineno, kind, snippet in scan_text(text, denylist):
            print(f"commit message:{lineno}: {kind}: {snippet}")
            problems += 1
    if args.paths:
        problems += check_blobs(gather_paths(args.paths), denylist)

    if problems:
        print(f"\nprivacy_check: {problems} problem(s). Fix the content before committing.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
