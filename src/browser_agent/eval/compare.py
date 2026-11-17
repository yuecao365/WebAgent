"""Compare arms that ran the same tasks several times each.

An arm is one configuration; its runs are repeats. Two arms are compared task by task
(paired), because the tasks differ far more from each other than the arms do, and
every difference is shown next to the run-to-run spread: the baseline alone moves by
several tasks between runs, so a smaller difference says nothing.

Definitions used in the tables:

success per run   tasks the evaluator scored successful in one run
all-of-n (pass^n) tasks successful in every run of the arm
any-of-n          tasks successful in at least one run
fixed             baseline succeeded in at most a third of its runs, the arm in at
                  least two thirds
broken            baseline in at least two thirds, the arm in at most a third
stabilized        baseline sometimes but not always, the arm always
unchanged         none of the three
A task can be both fixed and stabilized (baseline 1 of 3, arm 3 of 3).

An arm that was run only once is compared more strictly, because one run cannot tell a
change from chance where the baseline itself goes both ways:

fixed             baseline never succeeded, the arm's one run did
broken            baseline always succeeded, the arm's one run did not
mixed             baseline sometimes succeeded: whatever the arm's run did there is
                  within what the baseline does on its own
unchanged         baseline always or never succeeded, and the arm's run did the same
"""

from __future__ import annotations

import json
import random
import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from browser_agent.eval.aggregate import RunData, load_run, spread
from browser_agent.eval.failures import LABELS, classify, reviewed
from browser_agent.eval.memory_stats import run_memory_stats
from browser_agent.harness.events import read_events

LOW, HIGH = 1 / 3 + 1e-9, 2 / 3 - 1e-9
BOOTSTRAP_SAMPLES = 10_000
PER_TASK = ("steps", "model_calls", "seconds", "tokens", "usd")


@dataclass(frozen=True)
class Arm:
    """One configuration and its repeated runs."""

    name: str
    runs: Sequence[RunData]
    # Per run: task id -> number of model calls, counted from the event log.
    model_calls: Sequence[Mapping[int, int]]

    def task_ids(self) -> list[int]:
        return sorted({int(record["task_id"]) for run in self.runs for record in run.records})

    def successes(self) -> dict[int, int]:
        """Per task, in how many runs it succeeded."""
        counts: dict[int, int] = defaultdict(int)
        for run in self.runs:
            for record in run.records:
                counts[int(record["task_id"])] += bool(record["success"])
        return dict(counts)

    def rate(self) -> dict[int, float]:
        return {task: count / len(self.runs) for task, count in self.successes().items()}

    def per_task(self, key: str) -> dict[int, float]:
        """Per task, the mean of a number over the runs."""
        values: dict[int, list[float]] = defaultdict(list)
        for index, run in enumerate(self.runs):
            for record in run.records:
                task = int(record["task_id"])
                if key == "model_calls":
                    values[task].append(self.model_calls[index].get(task, record["steps"]))
                else:
                    values[task].append(float(record[key]))
        return {task: statistics.fmean(found) for task, found in values.items()}


def count_model_calls(run_dir: Path) -> dict[int, int]:
    """Model calls per task of a run, from its event logs (empty without traces)."""
    counts = {}
    for log in (run_dir / "traces").glob("*/events.jsonl"):
        counts[int(log.parent.name)] = sum(
            1 for event in read_events(log) if event["type"] == "model_call"
        )
    return counts


def load_arm(name: str, run_dirs: Sequence[Path]) -> Arm:
    return Arm(
        name, [load_run(path) for path in run_dirs], [count_model_calls(path) for path in run_dirs]
    )


# -- 1. per arm -----------------------------------------------------------------


def arm_summary(arm: Arm) -> dict[str, Any]:
    tasks = arm.task_ids()
    successes = arm.successes()
    runs = len(arm.runs)
    per_run = {
        "success": [float(run.summary["successes"]) for run in arm.runs],
        "steps": [float(run.summary["mean_steps"]) for run in arm.runs],
        "seconds": [float(run.summary["mean_seconds"]) for run in arm.runs],
        "tokens": [float(run.summary["mean_tokens"]) for run in arm.runs],
        "usd": [float(run.summary["mean_usd"]) for run in arm.runs],
        "model_calls": [
            statistics.fmean(
                calls.get(int(record["task_id"]), record["steps"]) for record in run.records
            )
            for run, calls in zip(arm.runs, arm.model_calls, strict=True)
        ],
    }
    total_usd = sum(float(run.summary["total_usd"]) for run in arm.runs)
    task_successes = sum(successes.values())
    return {
        "arm": arm.name,
        "runs": runs,
        "tasks": len(tasks),
        "per_run": per_run,
        "spread": {key: spread(values) for key, values in per_run.items()},
        "all_of_n": sum(1 for task in tasks if successes.get(task, 0) == runs),
        "any_of_n": sum(1 for task in tasks if successes.get(task, 0) > 0),
        "total_usd": total_usd,
        "usd_per_success": total_usd / task_successes if task_successes else float("nan"),
    }


def arms_table(arms: Sequence[Arm]) -> str:
    lines = [
        "| Arm | Runs | Success per run | Mean | Std dev | All-of-n | Any-of-n | Steps | "
        "Model calls | Seconds | Tokens | USD per task | USD per successful task |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm in arms:
        row = arm_summary(arm)
        stats = row["spread"]

        def cell(
            key: str, fmt: str, stats: Mapping[str, Any] = stats, runs: int = row["runs"]
        ) -> str:
            # One run has no spread to show.
            if runs == 1:
                return fmt.format(stats[key]["mean"])
            return f"{fmt.format(stats[key]['mean'])} ± {fmt.format(stats[key]['stdev'])}"

        per_run = ", ".join(f"{value:.0f}" for value in row["per_run"]["success"])
        deviation = "n/a" if row["runs"] == 1 else f"{stats['success']['stdev']:.1f}"
        lines.append(
            f"| {row['arm']} | {row['runs']} | {per_run} of {row['tasks']} | "
            f"{stats['success']['mean']:.1f} | {deviation} | "
            f"{row['all_of_n']} | {row['any_of_n']} | {cell('steps', '{:.1f}')} | "
            f"{cell('model_calls', '{:.1f}')} | {cell('seconds', '{:.1f}')} | "
            f"{cell('tokens', '{:,.0f}')} | {cell('usd', '{:.4f}')} | "
            f"{row['usd_per_success']:.4f} |"
        )
    return "\n".join(lines) + "\n"


# -- 2. paired per task -----------------------------------------------------------


def paired_outcomes(baseline: Arm, arm: Arm) -> dict[str, Any]:
    """Each shared task's successes in both arms, and which tasks changed how."""
    base_rate, arm_rate = baseline.rate(), arm.rate()
    base_count, arm_count = baseline.successes(), arm.successes()
    tasks = sorted(set(base_rate) & set(arm_rate))
    groups: dict[str, list[int]] = {
        "fixed": [], "broken": [], "stabilized": [], "mixed": [], "unchanged": [],
    }  # fmt: skip
    single = len(arm.runs) == 1
    for task in tasks:
        before, after = base_rate[task], arm_rate[task]
        if single:
            # One run of the arm: only the tasks the baseline always or never solved
            # can show a change.
            if 0 < before < 1:
                groups["mixed"].append(task)
                continue
            fixed, broken, stabilized = (
                before == 0 and after == 1,
                before == 1 and after == 0,
                False,
            )
        else:
            fixed = before <= LOW and after >= HIGH
            broken = before >= HIGH and after <= LOW
            stabilized = 0 < before < 1 and after == 1
        if fixed:
            groups["fixed"].append(task)
        if broken:
            groups["broken"].append(task)
        if stabilized:
            groups["stabilized"].append(task)
        if not (fixed or broken or stabilized):
            groups["unchanged"].append(task)
    return {
        "baseline": baseline.name,
        "arm": arm.name,
        "tasks": len(tasks),
        "runs": (len(baseline.runs), len(arm.runs)),
        "per_task": {task: (base_count[task], arm_count[task]) for task in tasks},
        **groups,
    }


def paired_table(
    pairs: Sequence[Mapping[str, Any]], causes: Mapping[str, Any] | None = None
) -> str:
    lines = [
        "| Arm vs baseline | Runs | Tasks | Fixed | Broken | Stabilized | Baseline mixed | "
        "Unchanged |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for pair in pairs:
        base_runs, arm_runs = pair["runs"]
        # With one run of the arm nothing can be called stabilized; with several, a
        # mixed baseline is not set apart.
        stabilized = "n/a" if arm_runs == 1 else str(len(pair["stabilized"]))
        mixed = str(len(pair["mixed"])) if arm_runs == 1 else "n/a"
        lines.append(
            f"| {pair['arm']} vs {pair['baseline']} | {arm_runs} vs {base_runs} | "
            f"{pair['tasks']} | {len(pair['fixed'])} | {len(pair['broken'])} | {stabilized} | "
            f"{mixed} | {len(pair['unchanged'])} |"
        )
    lines.append("")
    for pair in pairs:

        def listed(tasks: Sequence[int], pair: Mapping[str, Any] = pair) -> str:
            base_runs, arm_runs = pair["runs"]
            shown = [
                f"{task} ({pair['per_task'][task][0]}/{base_runs} → "
                f"{pair['per_task'][task][1]}/{arm_runs})"
                for task in tasks
            ]
            return ", ".join(shown) or "none"

        lines.append(f"**{pair['arm']} vs {pair['baseline']}**")
        lines.append(f"- fixed: {listed(pair['fixed'])}")
        lines.append(f"- broken: {listed(pair['broken'])}")
        if pair["runs"][1] > 1:
            lines.append(f"- stabilized: {listed(pair['stabilized'])}")
        else:
            lines.append(f"- baseline mixed (no conclusion from one run): {listed(pair['mixed'])}")
        arm_causes = (causes or {}).get(pair["arm"], {})
        for task in pair["broken"]:
            cause = arm_causes.get(str(task), "not reviewed")
            lines.append(f"  - broken {task}: {cause}")
        lines.append("")
    return "\n".join(lines)


# -- 3. paired efficiency ---------------------------------------------------------


def bootstrap_interval(
    values: Sequence[float], seed: int = 0, samples: int = BOOTSTRAP_SAMPLES
) -> tuple[float, float]:
    """A 95% interval for the mean of per-task differences, resampling the tasks."""
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    count = len(values)
    means = sorted(statistics.fmean(rng.choices(values, k=count)) for _ in range(samples))
    return means[int(0.025 * samples)], means[int(0.975 * samples) - 1]


def paired_efficiency(baseline: Arm, arm: Arm, seed: int = 0) -> dict[str, dict[str, float]]:
    """Per-task differences (arm minus baseline) of each task's mean over the runs."""
    result = {}
    for key in ("steps", "model_calls", "seconds"):
        before, after = baseline.per_task(key), arm.per_task(key)
        differences = [after[task] - before[task] for task in sorted(set(before) & set(after))]
        low, high = bootstrap_interval(differences, seed)
        result[key] = {
            "mean": statistics.fmean(differences) if differences else 0.0,
            "median": statistics.median(differences) if differences else 0.0,
            "low": low,
            "high": high,
            "tasks": len(differences),
        }
    return result


def efficiency_table(baseline: Arm, arms: Sequence[Arm]) -> str:
    lines = [
        f"Per-task difference from {baseline.name} (arm minus {baseline.name}); the interval "
        "is a 95% bootstrap interval of the mean over tasks.",
        "",
        "| Arm | Steps: mean | median | 95% interval | Model calls: mean | median | "
        "95% interval | Seconds: mean | median | 95% interval |",
        "|---|---:|---:|---|---:|---:|---|---:|---:|---|",
    ]
    for arm in arms:
        stats = paired_efficiency(baseline, arm)
        cells = []
        for key in ("steps", "model_calls", "seconds"):
            item = stats[key]
            cells += [
                f"{item['mean']:+.2f}",
                f"{item['median']:+.2f}",
                f"{item['low']:+.2f} to {item['high']:+.2f}",
            ]
        lines.append(f"| {arm.name} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


# -- 4. skills --------------------------------------------------------------------


def skills_table(arm_dirs: Mapping[str, Sequence[Path]]) -> str:
    """What the skill tools did in each arm, summed over its runs."""
    lines = [
        "| Arm | Task runs | Called load_skill | Called run_skill | Gate passed | Gate rejected | "
        "Code ran through | Code stopped | Handed to model | Successful after hand-over | "
        "Code ran through, task failed |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    notes = []
    for name, run_dirs in arm_dirs.items():
        total: Counter[str] = Counter()
        rejections: Counter[str] = Counter()
        wrong: list[str] = []
        for run_dir in run_dirs:
            stats = run_memory_stats(run_dir)
            for key in (
                "tasks", "tasks_loading_a_skill", "tasks_calling_run_skill", "gate_passed",
                "gate_rejected", "code_ran_through", "code_stopped_at_a_step",
            ):  # fmt: skip
                total[key] += stats[key]
            rejections.update(stats["rejections_by_check"])
            for task in stats["per_task"]:
                handed = any(outcome != "passed" for _, outcome in task["gate"]) or any(
                    not ok for _, ok in task["code"]
                )
                total["handed_tasks"] += handed
                total["handed_successes"] += handed and task["success"]
                if task["wrong_replay_candidate"]:
                    wrong.append(f"{run_dir.name.split('_', 1)[-1]}/{task['task_id']}")
        if not total["tasks_loading_a_skill"] and not total["tasks_calling_run_skill"]:
            continue
        lines.append(
            f"| {name} | {total['tasks']} | {total['tasks_loading_a_skill']} | "
            f"{total['tasks_calling_run_skill']} | {total['gate_passed']} | "
            f"{total['gate_rejected']} | {total['code_ran_through']} | "
            f"{total['code_stopped_at_a_step']} | {total['handed_tasks']} | "
            f"{total['handed_successes']}/{total['handed_tasks']} | {len(wrong)} |"
        )
        reasons = ", ".join(f"{check} {count}" for check, count in rejections.items()) or "none"
        notes.append(f"- {name}: gate rejections by check: {reasons}.")
        notes.append(f"  Code ran through but the task failed: {', '.join(wrong) or 'none'}.")
    return "\n".join([*lines, "", *notes]) + "\n"


# -- 7. failure classes -------------------------------------------------------------


def failure_classes(arm: Arm, labels: Mapping[str, Mapping[str, str]] | None = None) -> Counter:
    """Failed task runs by class: the reviewed label where there is one, else what can
    be told from the record."""
    counts: Counter[str] = Counter()
    for run in arm.runs:
        for record in run.records:
            if record["success"]:
                continue
            label = (labels or {}).get(str(record["task_id"]))
            if label is not None:
                found = reviewed(label["class"])
            else:
                found = classify(record, run.eval_details.get(str(record["task_id"])))
            assert found is not None
            counts[LABELS[found]] += 1
    return counts


def failure_table(
    arms: Sequence[Arm], labels: Mapping[str, Mapping[str, Mapping[str, str]]]
) -> str:
    counts = {arm.name: failure_classes(arm, labels.get(arm.name)) for arm in arms}
    names = sorted({name for found in counts.values() for name in found})
    head = " | ".join(f"{arm.name} ({len(arm.runs)} runs)" for arm in arms)
    lines = [f"| Failure class | {head} |", "|---|" + "---:|" * len(arms)]
    for name in names:
        lines.append(
            f"| {name} | " + " | ".join(str(counts[arm.name][name]) for arm in arms) + " |"
        )
    total = " | ".join(str(sum(counts[arm.name].values())) for arm in arms)
    lines.append(f"| All failed task runs | {total} |")
    return "\n".join(lines) + "\n"


# -- 8. the one-time cost of building memory ----------------------------------------


def build_costs(spend_path: Path, prefix: str = "memory_build_") -> dict[str, dict[str, Any]]:
    """Model calls and dollars of each memory build, by kind of call."""
    builds: dict[str, dict[str, Any]] = {}
    with spend_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            entry = json.loads(line)
            run = str(entry.get("run", ""))
            if not run.startswith(prefix):
                continue
            kind = str(entry.get("task_id", "")).split("-")[0]
            build = builds.setdefault(run[len(prefix) :], {"calls": 0, "usd": 0.0, "kinds": {}})
            build["calls"] += 1
            build["usd"] += entry["cost_usd"]
            by_kind = build["kinds"].setdefault(kind, {"calls": 0, "usd": 0.0})
            by_kind["calls"] += 1
            by_kind["usd"] += entry["cost_usd"]
    return builds


def build_cost_table(builds: Mapping[str, Mapping[str, Any]]) -> str:
    lines = ["| Build | Calls | USD | By kind of call |", "|---|---:|---:|---|"]
    for name, build in builds.items():
        kinds = ", ".join(
            f"{kind} {item['calls']} (${item['usd']:.4f})" for kind, item in build["kinds"].items()
        )
        lines.append(f"| {name} | {build['calls']} | {build['usd']:.4f} | {kinds} |")
    total = sum(build["usd"] for build in builds.values())
    lines.append(f"| All builds | {sum(b['calls'] for b in builds.values())} | {total:.4f} | |")
    return "\n".join(lines) + "\n"
