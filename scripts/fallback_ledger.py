"""Rebuild the fallback ledger of existing runs from their event logs.

    python scripts/fallback_ledger.py results/<run> [results/<run> ...] [--sum] [--save]

Prints one table per run; --sum prints one more for all the runs together. --save
also writes fallbacks.json and fallbacks.md into each run directory; the run's own
summary files are left as they are. The definitions are in
browser_agent/eval/fallbacks.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from browser_agent.eval.fallbacks import ledger_markdown, merge_ledgers, run_ledger


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("runs", nargs="+", type=Path, help="run directories under results/")
    parser.add_argument("--sum", action="store_true", help="also print the runs summed")
    parser.add_argument("--save", action="store_true", help="write fallbacks.json/.md per run")
    args = parser.parse_args(argv)

    ledgers = []
    for run_dir in args.runs:
        if not (run_dir / "traces").is_dir():
            print(f"{run_dir}: no traces directory, nothing to rebuild from", file=sys.stderr)
            return 1
        ledger = run_ledger(run_dir)
        ledgers.append(ledger)
        table = ledger_markdown(ledger)
        print(f"## {run_dir.name}\n\n{table}")
        if args.save:
            (run_dir / "fallbacks.json").write_text(json.dumps(ledger, indent=2), encoding="utf-8")
            (run_dir / "fallbacks.md").write_text(
                f"# Fallbacks: {run_dir.name}\n\n{table}", encoding="utf-8"
            )
    if args.sum and len(ledgers) > 1:
        print(f"## Sum of {len(ledgers)} runs\n\n{ledger_markdown(merge_ledgers(ledgers))}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
