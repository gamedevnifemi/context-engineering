#!/usr/bin/env python3
"""Run the housekeeping audit from a scheduler without installing the package.

Writes out/audit/report.md, inventory.json and plan.json under the repository. Scheduled by
scripts/schedule_audit.py; see docs/housekeeping.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ctxeng.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["audit", "--out", str(ROOT / "out" / "audit")] + sys.argv[1:]))
