"""Scan the traces of runs for pages loaded outside the agent's tab.

    uv run python scripts/scan_second_tab.py results/<run> [results/<run> ...]

For every task with an event log and a network trace on disk it lists the documents
that were loaded although the agent's tab was never seen at their address. A second
tab shows up this way in runs older than the new_tab event (log version 3).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from browser_agent.eval.tabscan import unshown_documents
from browser_agent.harness.events import read_events


def scan(run_dir: Path) -> tuple[int, int, dict[str, list[str]]]:
    """(tasks scanned, documents loaded, task -> documents the agent's tab never showed)."""
    tasks = documents = 0
    found: dict[str, list[str]] = {}
    for log in sorted(
        (run_dir / "traces").glob("*/events.jsonl"), key=lambda p: int(p.parent.name)
    ):
        har = log.parent / "network.har"
        if not har.exists():
            continue
        entries = json.loads(har.read_text(encoding="utf-8"))["log"]["entries"]
        tasks += 1
        documents += sum(1 for entry in entries if entry.get("_resourceType") == "Document")
        unshown = unshown_documents(read_events(log), entries)
        if unshown:
            found[log.parent.name] = unshown
    return tasks, documents, found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path)
    args = parser.parse_args(argv)
    for run_dir in args.runs:
        tasks, documents, found = scan(run_dir)
        print(
            f"{run_dir.name}: {tasks} tasks with traces, {documents} document requests, "
            f"{sum(len(urls) for urls in found.values())} not shown in the agent's tab"
        )
        for task, urls in found.items():
            for url in urls:
                print(f"  task {task}: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
