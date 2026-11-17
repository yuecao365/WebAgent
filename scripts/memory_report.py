"""What long-term memory did in one or more runs, from their event logs.

uv run python scripts/memory_report.py results/<run> [results/<run> ...]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from browser_agent.eval.memory_stats import memory_markdown, run_memory_stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("runs", nargs="+", type=Path)
    args = parser.parse_args(argv)
    for run_dir in args.runs:
        print(f"## {run_dir.name}\n")
        print(memory_markdown(run_memory_stats(run_dir)))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
