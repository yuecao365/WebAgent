"""Comparing arms run several times on the same tasks, on synthetic runs."""

from __future__ import annotations

import json

import pytest

from browser_agent.eval.aggregate import RunData
from browser_agent.eval.compare import (
    Arm,
    arm_summary,
    arms_table,
    bootstrap_interval,
    build_cost_table,
    build_costs,
    count_model_calls,
    efficiency_table,
    failure_table,
    load_arm,
    paired_efficiency,
    paired_outcomes,
    paired_table,
    skills_table,
)
from browser_agent.harness.events import EventLog


def run(name, outcomes, steps=None, usd=0.002):
    """A run of tasks 1..n; outcomes says which succeeded."""
    records = [
        {
            "task_id": task,
            "template_id": 1,
            "success": ok,
            "steps": (steps or {}).get(task, 5),
            "seconds": 10.0 * (steps or {}).get(task, 5),
            "tokens": 1000,
            "usd": usd,
            "finish_reason": "finished",
            "answered": True,
            "task_type": "retrieve",
        }
        for task, ok in enumerate(outcomes, start=1)
    ]
    count = len(records)
    summary = {
        "tasks": count,
        "successes": sum(outcomes),
        "mean_steps": sum(r["steps"] for r in records) / count,
        "mean_seconds": sum(r["seconds"] for r in records) / count,
        "mean_tokens": 1000.0,
        "mean_usd": usd,
        "total_usd": usd * count,
    }
    return RunData(name, summary, records, {})


def arm(name, *runs_outcomes, **kwargs):
    runs = [run(f"{name}_r{n}", outcomes, **kwargs) for n, outcomes in enumerate(runs_outcomes, 1)]
    return Arm(name, runs, [{} for _ in runs])


Y, N = True, False
#            task: 1  2  3  4  5  6
NONE = arm("none", [Y, N, Y, N, Y, N], [Y, N, N, N, Y, Y], [Y, N, Y, Y, Y, N])
#   successes:     3  0  2  1  3  1
MEMORY = arm("M2", [Y, Y, Y, Y, N, N], [Y, Y, Y, Y, N, Y], [Y, N, Y, Y, Y, N])
#   successes:     3  2  3  3  1  1


def test_an_arm_is_summarized_over_its_runs():
    summary = arm_summary(NONE)

    assert summary["per_run"]["success"] == [3.0, 3.0, 4.0]
    assert summary["spread"]["success"]["mean"] == pytest.approx(10 / 3)
    assert summary["spread"]["success"]["stdev"] == pytest.approx(0.577, abs=1e-3)
    # Tasks 1 and 5 succeeded in every run; only task 2 never did.
    assert (summary["all_of_n"], summary["any_of_n"]) == (2, 5)
    assert summary["usd_per_success"] == pytest.approx(0.002 * 18 / 10)


def test_tasks_are_paired_against_the_baseline():
    pair = paired_outcomes(NONE, MEMORY)

    assert pair["per_task"] == {1: (3, 3), 2: (0, 2), 3: (2, 3), 4: (1, 3), 5: (3, 1), 6: (1, 1)}
    # 2: never before, mostly now. 4: once before, always now (also stabilized).
    assert pair["fixed"] == [2, 4]
    assert pair["broken"] == [5]
    assert pair["stabilized"] == [3, 4]
    assert pair["unchanged"] == [1, 6]


def test_an_arm_with_two_runs_is_compared_by_rate():
    two_runs = arm("M3", [Y, Y, N, Y, N, N], [Y, N, Y, Y, N, N])

    pair = paired_outcomes(NONE, two_runs)

    # Task 2: 0/3 -> 1/2 is neither fixed nor broken. Task 5: 3/3 -> 0/2 is broken.
    assert pair["fixed"] == [4]
    assert pair["broken"] == [5]
    assert pair["runs"] == (3, 2)


def test_the_paired_table_lists_the_tasks_and_a_cause_for_each_broken_one():
    text = paired_table(
        [paired_outcomes(NONE, MEMORY)], {"M2": {"5": "ran a skill on the wrong page"}}
    )

    assert "| M2 vs none | 6 | 2 | 1 | 2 | 2 |" in text
    assert "- fixed: 2 (0/3 → 2/3), 4 (1/3 → 3/3)" in text
    assert "- broken: 5 (3/3 → 1/3)" in text
    assert "  - broken 5: ran a skill on the wrong page" in text
    assert "not reviewed" in paired_table([paired_outcomes(NONE, MEMORY)])


def test_efficiency_is_the_per_task_difference_with_a_bootstrap_interval():
    slow = arm("none", [Y, Y, Y], [Y, Y, Y], steps={1: 10, 2: 10, 3: 4})
    fast = arm("M2", [Y, Y, Y], [Y, Y, Y], steps={1: 4, 2: 6, 3: 4})

    stats = paired_efficiency(slow, fast)

    assert stats["steps"]["mean"] == pytest.approx(-10 / 3)
    assert stats["steps"]["median"] == -4
    assert stats["steps"]["low"] <= stats["steps"]["mean"] <= stats["steps"]["high"]
    assert stats["seconds"]["mean"] == pytest.approx(-100 / 3)
    # Without event logs the model calls are taken to be the steps.
    assert stats["model_calls"]["mean"] == stats["steps"]["mean"]
    assert "| M2 | -3.33 | -4.00 |" in efficiency_table(slow, [fast])


def test_the_bootstrap_interval_is_seeded_and_covers_a_constant():
    assert bootstrap_interval([2.0] * 8) == (2.0, 2.0)
    assert bootstrap_interval([1.0, 2.0, 3.0, 9.0], seed=1) == bootstrap_interval(
        [1.0, 2.0, 3.0, 9.0], seed=1
    )
    low, high = bootstrap_interval([1.0, 2.0, 3.0, 9.0])
    assert 1.0 <= low < high <= 9.0
    assert bootstrap_interval([]) == (0.0, 0.0)


def test_the_arms_table_has_a_row_per_arm():
    text = arms_table([NONE, MEMORY])

    assert "| none | 3 | 3, 3, 4 of 6 | 3.3 | 0.6 | 2 | 5 |" in text
    assert "| M2 | 3 | 4, 5, 4 of 6 | 4.3 | 0.6 | 3 | 6 |" in text


def write_run(root, name, tasks):
    """A run directory with records, a summary and event logs."""
    run_dir = root / name
    run_dir.mkdir(parents=True)
    records = []
    for task_id, success, events in tasks:
        log = EventLog(run_dir / "traces" / str(task_id) / "events.jsonl")
        log.append("task_start", goal="g", log_version=4)
        for kind, details in events:
            log.append(kind, **details)
        log.append("task_scored", success=success)
        records.append(
            {"task_id": task_id, "template_id": 1, "success": success, "steps": 3, "seconds": 9.0,
             "tokens": 100, "usd": 0.001, "finish_reason": "finished", "answered": True}
        )  # fmt: skip
    (run_dir / "records.jsonl").write_text(
        "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
    )
    summary = {"tasks": len(records), "successes": sum(r["success"] for r in records),
               "mean_steps": 3.0, "mean_seconds": 9.0, "mean_tokens": 100.0, "mean_usd": 0.001,
               "total_usd": 0.001 * len(records)}  # fmt: skip
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return run_dir


SKILL = {"skill": "show-report", "version": 2}


def test_skill_behaviour_is_counted_over_the_runs_of_an_arm(tmp_path):
    ran = [("model_call", {"step": 1}), ("gate_passed", SKILL),
           ("skill_code_run", {**SKILL, "ok": True}), ("model_call", {"step": 2})]  # fmt: skip
    rejected = [("model_call", {"step": 1}), ("skill_loaded", SKILL),
                ("gate_rejected", {**SKILL, "check": "url_pattern"}),
                ("skill_guided", {**SKILL, "reason": "url_pattern"})]  # fmt: skip
    stopped = [("gate_passed", SKILL), ("skill_code_run", {**SKILL, "ok": False}),
               ("skill_step_failed", {**SKILL, "step": 2}),
               ("skill_guided", {**SKILL, "reason": "step_failed"})]  # fmt: skip
    first = write_run(
        tmp_path, "2026-01-01_m2_r1", [(1, True, ran), (2, True, rejected), (3, True, [])]
    )
    second = write_run(
        tmp_path, "2026-01-01_m2_r2", [(1, False, ran), (2, False, stopped), (3, True, [])]
    )
    plain = write_run(tmp_path, "2026-01-01_none_r1", [(1, True, [("model_call", {"step": 1})])])

    text = skills_table({"none": [plain], "M2": [first, second]})

    # 6 task runs; 1 loaded; 4 called run_skill; gate 3 passed, 1 rejected; code ran
    # through twice and stopped once; 2 hand-overs of which 1 ended successfully; one
    # task failed although its code ran through.
    assert "| M2 | 6 | 1 | 4 | 3 | 1 | 2 | 1 | 2 | 1/2 | 1 |" in text
    assert "- M2: gate rejections by check: url_pattern 1." in text
    assert "Code ran through but the task failed: m2_r2/1." in text
    # An arm without skill activity has no row.
    assert "| none |" not in text
    assert count_model_calls(first) == {1: 2, 2: 1, 3: 0}
    loaded = load_arm("M2", [first, second])
    assert loaded.per_task("model_calls") == {1: 2.0, 2: 0.5, 3: 0.0}


def test_failures_are_counted_by_class_with_reviewed_labels_first():
    labels = {"M2": {"5": {"class": "action_not_done", "cause": "skill ran on the wrong page"}}}

    text = failure_table([NONE, MEMORY], labels)

    assert "| Failure class | none (3 runs) | M2 (3 runs) |" in text
    assert "| All failed task runs | 8 | 5 |" in text
    # Task 5 failed twice in M2 and carries the reviewed class there.
    assert "| Action not done or done wrongly | 0 | 2 |" in text


def test_the_cost_of_building_memory_is_summed_from_the_spend_log(tmp_path):
    entries = [
        {"run": "memory_build_learn_v3", "task_id": "induce-257", "cost_usd": 0.002},
        {"run": "memory_build_learn_v3", "task_id": "induce-268", "cost_usd": 0.003},
        {
            "run": "memory_build_learn_v3",
            "task_id": "verify-cancel-order-original",
            "cost_usd": 0.0002,
        },
        {"run": "memory_build_learn_v1", "task_id": "facts-257", "cost_usd": 0.001},
        {"run": "2026-11-16_m2_test_r1", "task_id": 108, "cost_usd": 0.5},
    ]
    path = tmp_path / "spend.jsonl"
    path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")

    builds = build_costs(path)

    assert builds["learn_v3"]["calls"] == 3
    assert builds["learn_v3"]["usd"] == pytest.approx(0.0052)
    assert builds["learn_v3"]["kinds"]["induce"] == {"calls": 2, "usd": pytest.approx(0.005)}
    # Task runs are per-task cost, not part of building memory.
    assert set(builds) == {"learn_v3", "learn_v1"}
    assert "| All builds | 4 | 0.0062 | |" in build_cost_table(builds)
