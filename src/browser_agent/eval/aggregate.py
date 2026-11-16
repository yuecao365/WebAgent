"""Numbers over several runs of the same tasks: mean, spread, and what keeps failing.

One run of a task set is one sample. Repeating it shows how much of a difference
between two arms is noise, so every table here gives the spread next to the mean.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from browser_agent.eval.failures import LABELS, FailureClass, classify, reviewed


@dataclass(frozen=True)
class RunData:
    """What one run directory holds, as far as the tables need it."""

    name: str
    summary: Mapping[str, Any]
    records: Sequence[Mapping[str, Any]]
    # The evaluator's output per task id, where the trace is still on disk.
    eval_details: Mapping[str, Mapping[str, Any]]


def load_run(run_dir: Path) -> RunData:
    records = [
        json.loads(line)
        for line in (run_dir / "records.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    details = {}
    for path in (run_dir / "traces").glob("*/eval_result.json"):
        details[path.parent.name] = json.loads(path.read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    return RunData(run_dir.name, summary, records, details)


METRICS: tuple[tuple[str, str, str], ...] = (
    ("Success", "successes", "{:.0f}"),
    ("Tokens per task", "mean_tokens", "{:,.0f}"),
    ("USD per task", "mean_usd", "{:.4f}"),
    ("Seconds per task", "mean_seconds", "{:.1f}"),
    ("Steps per task", "mean_steps", "{:.1f}"),
    ("Total USD", "total_usd", "{:.4f}"),
)


def spread(values: Sequence[float]) -> dict[str, float]:
    """Mean, sample standard deviation, lowest and highest of one number over the runs."""
    return {
        "mean": statistics.fmean(values) if values else 0.0,
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values, default=0.0),
        "max": max(values, default=0.0),
    }


def runs_table(runs: Sequence[RunData]) -> str:
    """One column per run, then the mean and the spread across the runs."""
    head = " | ".join(run.name for run in runs)
    lines = [
        f"| | {head} | Mean | Std dev | Min-max |",
        "|---|" + "---:|" * (len(runs) + 3),
    ]
    for label, key, fmt in METRICS:
        values = [float(run.summary[key]) for run in runs]
        stats = spread(values)
        cells = [fmt.format(value) for value in values]
        if key == "successes":
            cells = [
                f"{value:.0f}/{run.summary['tasks']}"
                for value, run in zip(values, runs, strict=True)
            ]
            mean, stdev = f"{stats['mean']:.1f}", f"{stats['stdev']:.1f}"
        else:
            mean, stdev = fmt.format(stats["mean"]), fmt.format(stats["stdev"])
        low_high = f"{fmt.format(stats['min'])}-{fmt.format(stats['max'])}"
        lines.append(f"| {label} | {' | '.join(cells)} | {mean} | {stdev} | {low_high} |")
    return "\n".join(lines) + "\n"


def template_success(runs: Sequence[RunData]) -> list[dict[str, Any]]:
    """Per template: successes out of (tasks x runs), and the count in each run."""
    per_run: dict[Any, list[int]] = defaultdict(lambda: [0] * len(runs))
    attempts: dict[Any, int] = defaultdict(int)
    for index, run in enumerate(runs):
        for record in run.records:
            template = record["template_id"]
            attempts[template] += 1
            per_run[template][index] += bool(record["success"])
    return [
        {
            "template_id": template,
            "successes": sum(per_run[template]),
            "attempts": attempts[template],
            "per_run": per_run[template],
        }
        for template in sorted(attempts, key=str)
    ]


def template_table(runs: Sequence[RunData], intents: Mapping[Any, str] | None = None) -> str:
    lines = ["| Template | Successes | Per run | Example task |", "|---:|---:|---|---|"]
    for row in template_success(runs):
        example = (intents or {}).get(row["template_id"], "")
        per_run = ", ".join(str(count) for count in row["per_run"])
        lines.append(
            f"| {row['template_id']} | {row['successes']}/{row['attempts']} | {per_run} | "
            f"{example} |"
        )
    return "\n".join(lines) + "\n"


def repeated_failures(runs: Sequence[RunData], at_least: int = 2) -> list[dict[str, Any]]:
    """Tasks that failed in at least this many runs, with the class each failure got."""
    failed: dict[Any, list[FailureClass]] = defaultdict(list)
    template: dict[Any, Any] = {}
    reasons: dict[Any, list[str]] = defaultdict(list)
    for run in runs:
        for record in run.records:
            task = record["task_id"]
            template[task] = record["template_id"]
            if record["success"]:
                continue
            found = classify(record, run.eval_details.get(str(task)))
            assert found is not None
            failed[task].append(found)
            reasons[task].append(f"{run.name}: {record['finish_reason']}")
    return [
        {
            "task_id": task,
            "template_id": template[task],
            "failures": len(classes),
            "runs": len(runs),
            "classes": [item.value for item in classes],
            "finish_reasons": reasons[task],
        }
        for task, classes in sorted(failed.items(), key=lambda item: str(item[0]))
        if len(classes) >= at_least
    ]


def failures_table(
    failures: Sequence[Mapping[str, Any]],
    labels: Mapping[str, Mapping[str, str]] | None = None,
) -> str:
    """Repeated failures grouped by class; a reviewed label replaces the automatic class.

    labels maps a task id to {"class": ..., "cause": ...}, written after reading the
    task's traces.
    """
    grouped: dict[FailureClass, list[str]] = defaultdict(list)
    for failure in failures:
        label = (labels or {}).get(str(failure["task_id"]))
        if label is not None:
            found = reviewed(label["class"])
            cause = label.get("cause", "")
        else:
            found = FailureClass(max(set(failure["classes"]), key=failure["classes"].count))
            cause = "not reviewed"
        grouped[found].append(
            f"| {failure['task_id']} | {failure['template_id']} | "
            f"{failure['failures']}/{failure['runs']} | {cause} |"
        )
    lines: list[str] = []
    for found in FailureClass:
        if found not in grouped:
            continue
        lines += [
            f"**{LABELS[found]}** ({len(grouped[found])})",
            "",
            "| Task | Template | Failed | Cause |",
            "|---:|---:|---:|---|",
            *grouped[found],
            "",
        ]
    return "\n".join(lines)
