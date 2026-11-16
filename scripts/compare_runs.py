"""Compare runs side by side: success, tokens by prompt section, cache, cost, time.

    uv run python scripts/compare_runs.py results/<run A> results/<run B> [...]

Prints Markdown. Every number is read from the runs' own records; nothing is
recomputed from prices, so a run made at other prices shows what it actually cost.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SECTIONS = ("system", "tools", "task", "history", "observation", "notes", "status")


def load(run_dir: Path) -> dict[str, Any]:
    records = [
        json.loads(line)
        for line in (run_dir / "records.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    return {"name": run_dir.name, "records": records, "summary": summary}


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def table(header: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join(["---"] + ["---:"] * (len(header) - 1)) + "|",
    ]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def overview(runs: list[dict[str, Any]]) -> str:
    def row(label: str, value: Any) -> list[str]:
        return [label, *[value(run) for run in runs]]

    def usage(run: dict[str, Any], key: str) -> float:
        return mean([record.get("usage", {}).get(key, 0) for record in run["records"]])

    rows = [
        row("Success", lambda r: f"{r['summary']['successes']}/{r['summary']['tasks']}"),
        row("Tokens per task", lambda r: f"{r['summary']['mean_tokens']:,.0f}"),
        row("  input, uncached", lambda r: f"{usage(r, 'input_tokens'):,.0f}"),
        row("  input, read from cache", lambda r: f"{usage(r, 'cached_input_tokens'):,.0f}"),
        row("  input, written to cache", lambda r: f"{usage(r, 'cache_write_tokens'):,.0f}"),
        row("  output", lambda r: f"{usage(r, 'output_tokens'):,.0f}"),
        row("Cache hit rate", lambda r: f"{r['summary'].get('cache_hit_rate', 0):.0%}"),
        row("USD per task", lambda r: f"{r['summary']['mean_usd']:.4f}"),
        row("Seconds per task", lambda r: f"{r['summary']['mean_seconds']:.0f}"),
        row("Steps per task", lambda r: f"{r['summary']['mean_steps']:.1f}"),
        row("Total USD", lambda r: f"{r['summary']['total_usd']:.4f}"),
    ]
    return table(["", *[run["name"] for run in runs]], rows)


def sections(runs: list[dict[str, Any]]) -> str:
    rows = []
    for name in SECTIONS:
        values = [run["summary"].get("mean_section_tokens", {}).get(name, 0) for run in runs]
        if any(values):
            rows.append([name, *[f"{value:,.0f}" for value in values]])
    return table(["Prompt tokens per task (estimate)", *[run["name"] for run in runs]], rows)


def per_task(runs: list[dict[str, Any]]) -> str:
    task_ids = [record["task_id"] for record in runs[0]["records"]]
    header = ["Task"]
    for run in runs:
        header += [f"{run['name']}: ok", "tokens", "USD", "s", "steps", "finish"]
    rows = []
    for task_id in task_ids:
        row = [str(task_id)]
        for run in runs:
            record = next((r for r in run["records"] if r["task_id"] == task_id), None)
            if record is None:
                row += ["-"] * 6
                continue
            row += [
                "yes" if record["success"] else "no",
                f"{record['tokens']:,}",
                f"{record['usd']:.4f}",
                f"{record['seconds']:.0f}",
                str(record["steps"]),
                record["finish_reason"],
            ]
        rows.append(row)
    return table(header, rows)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    runs = [load(Path(arg)) for arg in argv[1:]]
    print(overview(runs), sections(runs), per_task(runs), sep="\n\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
