"""The tables of the memory experiment, from the run directories.

    uv run python scripts/memory_arms_report.py --arms configs/memory_arms.json

The arms file names the runs of every arm:

    {
      "test":  {"none": ["results/<run>", ...], "M1": [...], "M2": [...], "C": [...]},
      "probe": {"none": [...], "M2": [...]},
      "baseline": "none",
      "two_by_two": {"memory off": {"effort low": "none", "effort high": "C"},
                     "memory on":  {"effort low": "M2",   "effort high": "M2-high"}},
      "causes": "results/memory_arms_causes.json",
      "failure_labels": "results/memory_arms_failures.json"
    }

"causes" holds one line per broken task, read from its trace:
{"<arm>": {"<task id>": "<cause>"}}. "failure_labels" holds reviewed failure classes
per arm: {"<arm>": {"<task id>": {"class": ..., "cause": ...}}}. Both are optional;
without them a broken task says "not reviewed" and failures get the class that can be
told from the record alone.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from browser_agent.eval.compare import (
    Arm,
    arm_summary,
    arms_table,
    build_cost_table,
    build_costs,
    efficiency_table,
    failure_table,
    load_arm,
    paired_outcomes,
    paired_table,
    skills_table,
)


def _optional(path: str | None) -> dict[str, Any]:
    if not path or not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def two_by_two(arms: dict[str, Arm], layout: dict[str, dict[str, str]]) -> str:
    """Memory by effort: mean success per run and cost per successful task in each cell."""
    columns = list(next(iter(layout.values())))
    lines = [f"| | {' | '.join(columns)} |", "|---|" + "---|" * len(columns)]
    for row, cells in layout.items():
        shown = []
        for column in columns:
            arm = arms.get(cells[column])
            if arm is None:
                shown.append(f"{cells[column]}: not run")
                continue
            summary = arm_summary(arm)
            success = summary["spread"]["success"]
            shown.append(
                f"{arm.name}: {success['mean']:.1f} ± {success['stdev']:.1f} of "
                f"{summary['tasks']}; ${summary['usd_per_success']:.4f} per successful task"
            )
        lines.append(f"| {row} | " + " | ".join(shown) + " |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arms", type=Path, required=True)
    parser.add_argument("--spend", type=Path, default=Path("results/spend.jsonl"))
    args = parser.parse_args(argv)
    config = json.loads(args.arms.read_text(encoding="utf-8"))
    base_name = config.get("baseline", "none")
    causes = _optional(config.get("causes"))
    labels = _optional(config.get("failure_labels"))

    for task_set in ("test", "probe"):
        named = config.get(task_set) or {}
        if not named:
            continue
        dirs = {name: [Path(path) for path in paths] for name, paths in named.items()}
        arms = {name: load_arm(name, paths) for name, paths in dirs.items()}
        baseline = arms[base_name]
        others = [arm for name, arm in arms.items() if name != base_name]
        print(f"# {task_set.capitalize()} tasks\n")
        print("## 1. Per arm\n")
        print(arms_table(list(arms.values())))
        print(
            "Success per run is the number of tasks the evaluator scored successful; the "
            "mean and standard deviation are over the arm's runs. A difference between two "
            "arms smaller than those standard deviations is not an improvement.\n"
        )
        print(f"## 2. Paired per task against {base_name}\n")
        pairs = [paired_outcomes(baseline, arm) for arm in others]
        print(paired_table(pairs, causes.get(task_set, causes)))
        print("## 3. Paired efficiency\n")
        print(efficiency_table(baseline, others))
        if task_set == "test":
            print("## 4. Skills\n")
            print(skills_table(dirs))
            layout = config.get("two_by_two")
            if layout:
                print("## 5. Memory by effort\n")
                print(two_by_two(arms, layout))
                effort_pairs = [
                    paired_outcomes(arms[a], arms[b])
                    for a, b in config.get("extra_pairs", [])
                    if a in arms and b in arms
                ]
                if effort_pairs:
                    print(paired_table(effort_pairs, causes.get(task_set, causes)))
            print("## 7. Failure classes\n")
            shown = [arms[name] for name in config.get("failure_arms", [base_name]) if name in arms]
            print(failure_table(shown, labels))

    if args.spend.exists():
        print("# 8. One-time cost of building memory\n")
        print(build_cost_table(build_costs(args.spend)))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
