#!/usr/bin/env python3
"""Schedule the weekly housekeeping audit.

On Windows this registers a Task Scheduler entry that runs scripts/run_audit.py with the current
Python interpreter. Elsewhere it prints the crontab line to add. Pass --remove to delete the task.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK_NAME = "ctxeng-audit"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--day", default="SUN", help="weekday (Windows: MON..SUN; cron: 0..6)")
    ap.add_argument("--time", default="09:00", help="24-hour HH:MM")
    ap.add_argument("--remove", action="store_true")
    args = ap.parse_args(argv)

    runner = ROOT / "scripts" / "run_audit.py"
    if os.name == "nt":
        if args.remove:
            r = subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], capture_output=True, text=True)
        else:
            command = f'"{sys.executable}" "{runner}"'
            r = subprocess.run(["schtasks", "/Create", "/F", "/SC", "WEEKLY", "/D", args.day, "/ST", args.time,
                                "/TN", TASK_NAME, "/TR", command], capture_output=True, text=True)
        print((r.stdout or r.stderr).strip())
        return r.returncode
    hour, minute = args.time.split(":")
    day = {"SUN": 0, "MON": 1, "TUE": 2, "WED": 3, "THU": 4, "FRI": 5, "SAT": 6}.get(args.day.upper(), args.day)
    if args.remove:
        print(f"Remove the line containing {runner} from `crontab -e`.")
    else:
        print("Add this line with `crontab -e`:")
        print(f"{int(minute)} {int(hour)} * * {day} {sys.executable} {runner}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
