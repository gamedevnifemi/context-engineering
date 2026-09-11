"""Find Claude Code's local transcript store without assuming anything about the machine.

Claude Code keeps one folder per project under ``<config>/projects/``, named after the project's
working directory, and one ``<session-id>.jsonl`` per session inside it. Subagent and workflow
transcripts sit in a folder named after the session. ``<config>`` is ``~/.claude`` unless the
``CLAUDE_CONFIG_DIR`` environment variable says otherwise.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


def config_dir() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env).expanduser() if env else Path.home() / ".claude"


def projects_dir(root: Path | None = None) -> Path:
    return (root or config_dir()) / "projects"


@dataclass(frozen=True)
class SessionRef:
    project_slug: str
    session_id: str
    path: Path
    subagent_paths: tuple[Path, ...] = ()

    @property
    def size_bytes(self) -> int:
        return self.path.stat().st_size

    @property
    def mtime(self) -> float:
        return self.path.stat().st_mtime


def iter_sessions(projects: Path | None = None, project: str | None = None) -> Iterator[SessionRef]:
    """Yield every main-session transcript, optionally filtered by a project-slug substring."""
    base = projects or projects_dir()
    if not base.is_dir():
        return
    for proj in sorted(p for p in base.iterdir() if p.is_dir()):
        if project and project.lower() not in proj.name.lower():
            continue
        for f in sorted(proj.glob("*.jsonl")):
            side = proj / f.stem
            subs = tuple(sorted(side.rglob("*.jsonl"))) if side.is_dir() else ()
            yield SessionRef(proj.name, f.stem, f, subs)


def find_sessions(prefix: str, projects: Path | None = None) -> list[SessionRef]:
    """Sessions whose id starts with ``prefix``."""
    return [s for s in iter_sessions(projects) if s.session_id.startswith(prefix)]
