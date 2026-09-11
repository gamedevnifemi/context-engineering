"""Patterns for things that identify a person or a machine.

Shared by the pre-commit privacy scanner and by report redaction, so there is exactly one
definition of what counts as personal.
"""
from __future__ import annotations

import re

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Addresses that are safe to publish: GitHub's no-reply relay, tooling attribution, RFC 2606 domains.
ALLOWED_EMAIL_SUFFIXES = (
    "@users.noreply.github.com",
    "noreply@anthropic.com",
    "@example.com",
    "@example.org",
    "@example.net",
)

# Home-directory paths on Windows, macOS, and Linux. The captured group is the username.
HOME_PATHS = (
    re.compile(r"(?i)\b[a-z]:[\\/]+users[\\/]+([^\\/\s\"'`<>|]+)"),
    re.compile(r"/(?:home|Users)/([^/\s\"'`<>|]+)"),
)

# Claude Code names each project folder after the working directory, so the slug embeds the
# username, e.g. ``C--Users-<name>-code-project``.
PROJECT_SLUG = re.compile(r"(?i)\b[a-z]--users-([a-z0-9._~<>$%{}]+)-")

# Values allowed in a username position because they are obviously placeholders.
PLACEHOLDER_USERS = {
    "<you>", "<user>", "<username>", "<name>", "you", "user", "username", "yourname", "name",
    "public", "default", "$user", "%username%", "${user}", "{user}", "me", "...", "*",
}

CREDENTIALS = (
    ("anthropic api key", re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}")),
    ("github token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}")),
    ("github fine-grained token", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("aws access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)


def _is_placeholder(user: str) -> bool:
    u = user.strip().lower()
    return u in PLACEHOLDER_USERS or any(ch in u for ch in "<>$%{}")


def find_personal(text: str) -> list[tuple[str, str]]:
    """Return ``(kind, matched_text)`` for every personal-looking fragment in ``text``."""
    hits: list[tuple[str, str]] = []
    for m in EMAIL.finditer(text):
        addr = m.group(0)
        if not addr.lower().endswith(ALLOWED_EMAIL_SUFFIXES):
            hits.append(("email address", addr))
    for pat in HOME_PATHS:
        for m in pat.finditer(text):
            if not _is_placeholder(m.group(1)):
                hits.append(("home-directory path", m.group(0)))
    for m in PROJECT_SLUG.finditer(text):
        if not _is_placeholder(m.group(1)):
            hits.append(("project slug with username", m.group(0)))
    for kind, pat in CREDENTIALS:
        for m in pat.finditer(text):
            hits.append((kind, m.group(0)[:12] + "..."))
    return hits


def scrub(text: str) -> str:
    """Replace personal fragments with neutral placeholders."""
    def email_sub(m: re.Match[str]) -> str:
        return m.group(0) if m.group(0).lower().endswith(ALLOWED_EMAIL_SUFFIXES) else "<email>"

    def user_sub(m: re.Match[str]) -> str:
        if _is_placeholder(m.group(1)):
            return m.group(0)
        head = m.group(0)[: m.start(1) - m.start(0)]
        tail = m.group(0)[m.end(1) - m.start(0):]
        return head + "<user>" + tail

    out = EMAIL.sub(email_sub, text)
    for pat in HOME_PATHS:
        out = pat.sub(user_sub, out)
    out = PROJECT_SLUG.sub(user_sub, out)
    for _kind, pat in CREDENTIALS:
        out = pat.sub("<redacted>", out)
    return out
