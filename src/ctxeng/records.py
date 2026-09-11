"""Typed view of the parts of a transcript that matter for context accounting."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone


def parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


@dataclass
class Usage:
    """Token accounting for one API call, as reported by the model provider."""
    input: int = 0
    cache_read: int = 0
    cache_creation: int = 0
    output: int = 0
    thinking: int = 0

    @property
    def context(self) -> int:
        """Everything the model was given on this call: the live context window size."""
        return self.input + self.cache_read + self.cache_creation

    @classmethod
    def from_api(cls, u: dict) -> "Usage":
        details = u.get("output_tokens_details") or {}
        return cls(
            input=int(u.get("input_tokens") or 0),
            cache_read=int(u.get("cache_read_input_tokens") or 0),
            cache_creation=int(u.get("cache_creation_input_tokens") or 0),
            output=int(u.get("output_tokens") or 0),
            thinking=int(details.get("thinking_tokens") or 0),
        )

    def merge_max(self, other: "Usage") -> None:
        """Keep the larger figure per field when the same call is reported more than once."""
        for name in ("input", "cache_read", "cache_creation", "output", "thinking"):
            setattr(self, name, max(getattr(self, name), getattr(other, name)))


@dataclass
class ToolUse:
    id: str
    name: str
    input_chars: int
    request_id: str
    prompt_index: int
    timestamp: str


@dataclass
class ToolResult:
    tool_use_id: str
    tool_name: str
    chars: int
    is_error: bool
    prompt_index: int
    timestamp: str


@dataclass
class ApiCall:
    """One request to the model. Several transcript records can belong to the same call."""
    index: int
    request_id: str
    timestamp: str
    model: str
    effort: str | None
    version: str | None
    usage: Usage
    stop_reason: str | None
    prompt_index: int
    text_chars: int = 0
    thinking_chars: int = 0
    tool_uses: list[ToolUse] = field(default_factory=list)


@dataclass
class Prompt:
    """A user-side message that starts a turn. ``kind`` separates real prompts from machinery."""
    index: int
    timestamp: str
    chars: int
    kind: str  # user | compaction_summary | command | reminder | empty


@dataclass
class Attachment:
    """Context injected by Claude Code itself: system prompt, instructions, listings, reminders."""
    kind: str
    chars: int
    prompt_index: int
    timestamp: str


@dataclass
class Compaction:
    timestamp: str
    trigger: str
    pre_tokens: int
    post_tokens: int
    dropped_tokens: int
    duration_ms: int
    prompt_index: int
    api_call_index: int
    summary_chars: int = 0

    @property
    def retained_fraction(self) -> float:
        return self.post_tokens / self.pre_tokens if self.pre_tokens else 0.0


@dataclass
class SubagentSummary:
    agent_id: str
    api_calls: int
    output_tokens: int
    thinking_tokens: int
    peak_context: int
    tool_uses: int
    models: Counter = field(default_factory=Counter)


@dataclass
class Session:
    project_slug: str
    session_id: str
    path: str
    first_ts: str | None = None
    last_ts: str | None = None
    models: Counter = field(default_factory=Counter)
    efforts: Counter = field(default_factory=Counter)
    versions: Counter = field(default_factory=Counter)
    record_types: Counter = field(default_factory=Counter)
    system_subtypes: Counter = field(default_factory=Counter)
    prompts: list[Prompt] = field(default_factory=list)
    api_calls: list[ApiCall] = field(default_factory=list)
    tool_uses: list[ToolUse] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)
    compactions: list[Compaction] = field(default_factory=list)
    subagents: list[SubagentSummary] = field(default_factory=list)

    @property
    def user_prompts(self) -> list[Prompt]:
        return [p for p in self.prompts if p.kind == "user"]
