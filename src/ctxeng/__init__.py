"""ctxeng: diagnostics for how Claude Code sessions consume context and what compaction costs.

The package reads Claude Code's own transcript files in place. Nothing is copied, and every
identifier that leaves the local machine goes through ``ctxeng.redact``.
"""

__version__ = "0.1.0"
