"""Tables over several runs of the same tasks, in Markdown.

    python scripts/baseline_report.py results/<r1> results/<r2> results/<r3> \
        [--labels results/<file>.json] [--subset configs/subset.json]

Prints: the numbers of each run with the mean and the spread; success per template;
the fallback ledger summed over the runs; and every task that failed in at least two
runs, grouped by failure class. --labels names a JSON file of reviewed causes,
{"<task id>": {"class": "<failure class>", "cause": "<one line>"}}; without a label a
task gets the class that can be told without reading its trace.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from browser_agent.eval.aggregate import (
    failures_table,
    load_run,
    repeated_failures,
    runs_table,
    template_table,
)
from browser_agent.eval.fallbacks import ledger_markdown, merge_ledgers, run_ledger


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--labels", type=Path, help="reviewed failure causes (JSON)")
    parser.add_argument("--subset", type=Path, default=Path("configs/subset.json"))
    parser.add_argument("--at-least", type=int, default=2, help="failed in this many runs")
    args = parser.parse_args(argv)

    runs = [load_run(run_dir) for run_dir in args.runs]
    labels = json.loads(args.labels.read_text(encoding="utf-8")) if args.labels else {}
    intents: dict[int, str] = {}
    if args.subset.exists():
        subset = json.loads(args.subset.read_text(encoding="utf-8"))
        for entry in subset["tasks"] if isinstance(subset, dict) else subset:
            intents.setdefault(entry["template_id"], entry.get("intent", ""))

    print("## Runs\n")
    print(runs_table(runs))
    print("## Success per template\n")
    print(template_table(runs, intents))
    print(f"## Fallbacks, summed over {len(runs)} runs\n")
    print(ledger_markdown(merge_ledgers([run_ledger(run_dir) for run_dir in args.runs])))
    print(f"## Tasks that failed in at least {args.at_least} of {len(runs)} runs\n")
    print(failures_table(repeated_failures(runs, args.at_least), labels))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
