#!/usr/bin/env python3
"""Content checks for this repository.

Scans text that is about to be committed, or any path on demand, and exits non-zero when it finds
something that should not be published. The policy, what is checked, and how to configure the
local part of it are described in docs/privacy.md.

Usage:
  privacy_check.py --staged                   files staged for commit
  privacy_check.py --message FILE             a commit message
  privacy_check.py [--no-snippets] PATH ...   files or directories
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ctxeng.patterns import find_personal  # noqa: E402

# Paths that are never committed, whatever they contain.
FORBIDDEN_PATHS = (
    (re.compile(r"\.jsonl$"), "transcript"),
    (re.compile(r"(^|/)out/"), "generated output"),
    (re.compile(r"(^|/)\.ctxeng/"), "local configuration"),
    (re.compile(r"(^|/)(denylist|terms)\.txt$", re.I), "local configuration"),
)

# Images are accepted but cannot be read as text, so they are listed for manual review.
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

# Formats that cannot be scanned are not accepted at all.
UNSCANNABLE_SUFFIXES = {
    ".pdf", ".zip", ".gz", ".tgz", ".tar", ".7z", ".rar", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".woff", ".woff2", ".ttf", ".otf", ".pyc", ".pkl", ".db", ".sqlite",
}

_INVISIBLE = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad]")  # zero-width and soft-hyphen characters


def normalize(text: str) -> str:
    """Fold look-alike characters and strip invisible ones so they cannot hide a match."""
    return _INVISIBLE.sub("", unicodedata.normalize("NFKC", text))


def terms_path() -> Path:
    env = os.environ.get("CTXENG_TERMS_FILE")
    if env:
        return Path(env).expanduser()
    return Path(os.environ.get("CTXENG_HOME", "~/.ctxeng")).expanduser() / "terms.txt"


def load_terms() -> list[re.Pattern[str]]:
    """Locally configured terms, from the environment and/or the local file. Never committed."""
    raw: list[str] = []
    inline = os.environ.get("CTXENG_TERMS")
    if inline:
        raw += inline.splitlines()
    path = terms_path()
    if path.is_file():
        raw += path.read_text(encoding="utf-8").splitlines()
    patterns: list[re.Pattern[str]] = []
    for line in raw:
        term = normalize(line.strip())
        if not term or term.startswith("#"):
            continue
        if re.fullmatch(r"[\w.+-]+", term):
            patterns.append(re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.I))
        else:
            patterns.append(re.compile(re.escape(term), re.I))
    return patterns


def scan_text(text: str, terms: list[re.Pattern[str]]) -> list[tuple[int, str, str]]:
    """Return (line_number, kind, snippet) for every hit."""
    hits: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(normalize(text).splitlines(), start=1):
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
    images: list[str] = []
    for rel, data in items:
        rel_posix = rel.replace("\\", "/")
        for rule, why in FORBIDDEN_PATHS:
            if rule.search(rel_posix):
                print(f"{rel}: not accepted ({why})")
                problems += 1
        suffix = Path(rel).suffix.lower()
        if suffix in UNSCANNABLE_SUFFIXES:
            print(f"{rel}: not accepted (cannot be scanned)")
            problems += 1
            continue
        if suffix in IMAGE_SUFFIXES:
            images.append(rel)
            continue
        if b"\0" in data[:8000]:
            print(f"{rel}: not accepted (binary content cannot be scanned)")
            problems += 1
            continue
        for lineno, kind, snippet in scan_text(data.decode("utf-8", "replace"), terms):
            print(f"{rel}:{lineno}: {kind}: {snippet}" if snippets else f"{rel}:{lineno}: {kind}")
            problems += 1
    for rel in images:
        print(f"note: {rel} is an image and was not scanned; review it by eye", file=sys.stderr)
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
    ap.add_argument("--no-snippets", action="store_true",
                    help="report locations and kinds only, never the matched text")
    ap.add_argument("paths", nargs="*", help="files or directories to scan")
    args = ap.parse_args(argv)

    terms = load_terms()
    if not terms:
        print("content checks: no local terms configured; built-in checks only (see docs/privacy.md)",
              file=sys.stderr)
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
        print(f"\ncontent checks: {problems} problem(s); see docs/privacy.md", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
