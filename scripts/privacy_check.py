#!/usr/bin/env python3
"""Content checks for this repository. See docs/privacy.md.

Usage:
  privacy_check.py --staged
  privacy_check.py --message FILE
  privacy_check.py [--no-snippets] PATH ...
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

NOT_TRACKED = re.compile(r"\.jsonl$|(^|/)out/")


def terms_path() -> Path:
    env = os.environ.get("CTXENG_TERMS_FILE")
    if env:
        return Path(env).expanduser()
    return Path(os.environ.get("CTXENG_HOME", "~/.ctxeng")).expanduser() / "terms.txt"


def load_terms() -> list[re.Pattern[str]]:
    raw: list[str] = []
    inline = os.environ.get("CTXENG_TERMS")
    if inline:
        raw += inline.splitlines()
    path = terms_path()
    if path.is_file():
        raw += path.read_text(encoding="utf-8").splitlines()
    patterns: list[re.Pattern[str]] = []
    for line in raw:
        term = line.strip()
        if not term or term.startswith("#"):
            continue
        if re.fullmatch(r"[\w.+-]+", term):
            patterns.append(re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.I))
        else:
            patterns.append(re.compile(re.escape(term), re.I))
    return patterns


def scan_text(text: str, terms: list[re.Pattern[str]]) -> list[tuple[int, str, str]]:
    hits: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for kind, match in find_personal(line):
            hits.append((lineno, kind, match))
        for pat in terms:
            m = pat.search(line)
            if m:
                hits.append((lineno, "configured term", m.group(0)))
    return hits


def staged_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
        check=True, capture_output=True,
    ).stdout.decode("utf-8", "replace")
    return [p for p in out.split("\0") if p]


def staged_content(path: str) -> bytes:
    return subprocess.run(["git", "show", f":{path}"], check=True, capture_output=True).stdout


def check_blobs(items: list[tuple[str, bytes]], terms: list[re.Pattern[str]],
                snippets: bool = True) -> int:
    problems = 0
    for rel, data in items:
        if NOT_TRACKED.search(rel.replace("\\", "/")):
            print(f"{rel}: not accepted")
            problems += 1
            continue
        if b"\0" in data[:8000]:
            continue
        for lineno, kind, snippet in scan_text(data.decode("utf-8", "replace"), terms):
            print(f"{rel}:{lineno}: {kind}: {snippet}" if snippets else f"{rel}:{lineno}: {kind}")
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
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--message", metavar="FILE")
    ap.add_argument("--no-snippets", action="store_true")
    ap.add_argument("paths", nargs="*")
    args = ap.parse_args(argv)

    terms = load_terms()
    snippets = not args.no_snippets
    problems = 0
    if args.staged:
        problems += check_blobs([(p, staged_content(p)) for p in staged_files()], terms, snippets)
    if args.message:
        text = Path(args.message).read_text(encoding="utf-8", errors="replace")
        for lineno, kind, snippet in scan_text(text, terms):
            print(f"commit message:{lineno}: {kind}: {snippet}" if snippets
                  else f"commit message:{lineno}: {kind}")
            problems += 1
    if args.paths:
        problems += check_blobs(gather_paths(args.paths), terms, snippets)

    if problems:
        print(f"\n{problems} problem(s); see docs/privacy.md", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
