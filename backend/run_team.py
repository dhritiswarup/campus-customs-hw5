"""Run the Campus Customs agent team once from the command line.

    .venv/Scripts/python.exe backend/run_team.py                 # work every open ticket
    .venv/Scripts/python.exe backend/run_team.py --task "..."    # custom task for the Boss
    .venv/Scripts/python.exe backend/run_team.py --db path.db    # use a scratch DB copy

Every step is appended to output/audit_trail.json (or $CAMPUS_CUSTOMS_AUDIT).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents import run_team  # noqa: E402
from agents.loop import DEFAULT_TASK  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", default=DEFAULT_TASK, help="Instruction for the Boss.")
    parser.add_argument("--db", default=None, help="Database file for the MCP server (default: data/campus_customs_new.db).")
    args = parser.parse_args()
    result = asyncio.run(run_team(args.task, db_path=args.db))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
