"""Failure classes and the tables over repeated runs, from synthetic records."""

from __future__ import annotations

import json

import pytest

from browser_agent.eval.aggregate import (
    RunData,
    failures_table,
    load_run,
    repeated_failures,
    runs_table,
    spread,
    template_success,
    template_table,
)
from browser_agent.eval.failures import LABELS, NEEDS_REVIEW, FailureClass, classify, reviewed


def record(task_id, template_id, success, finish_reason="finished"):
    return {
        "task_id": task_id,
        "template_id": template_id,
        "success": success,
        "finish_reason": finish_reason,
    }


def answer(actual_status, expected_status="success", status="failure"):
    return {
        "evaluator_name": "AgentResponseEvaluator",
        "status": status,
        "actual_normalized": {"status": actual_status},
        "expected": {"status": expected_status},
    }


NETWORK_FAILED = {"evaluator_name": "NetworkEventEvaluator", "status": "failure"}


def detail(*evaluators):
    return {"evaluators_results": list(evaluators)}


# -- classes -----------------------------------------------------------------------


def test_a_successful_task_has_no_failure_class():
    assert classify(record(1, 10, True)) is None


@pytest.mark.parametrize(
    ("finish_reason", "expected"),
    [
        ("harness_error", FailureClass.HARNESS_ERROR),
        ("budget_steps", FailureClass.OVER_BUDGET),
        ("budget_tokens", FailureClass.OVER_BUDGET),
        ("stuck", FailureClass.OVER_BUDGET),
        ("model_error", FailureClass.OVER_BUDGET),
    ],
)
def test_how_the_task_ended_decides_first(finish_reason, expected):
    failed = record(1, 10, False, finish_reason)

    assert classify(failed, detail(answer("success"))) is expected


def test_an_error_status_where_success_was_expected_is_giving_up():
    failed = record(1, 10, False)

    assert classify(failed, detail(answer("not_found_error"))) is FailureClass.GAVE_UP
    assert classify(failed, detail(answer("unknown_error"))) is FailureClass.GAVE_UP


def test_an_accepted_answer_with_the_action_missing_is_an_action_not_done():
    failed = record(1, 10, False)
    accepted = answer("success", status="success")

    assert classify(failed, detail(accepted, NETWORK_FAILED)) is FailureClass.ACTION_NOT_DONE


def test_a_wrong_answer_is_left_for_review():
    failed = record(1, 10, False)

    found = classify(failed, detail(answer("success")))

    assert found is FailureClass.WRONG_ANSWER_UNREVIEWED
    assert found not in NEEDS_REVIEW
    # Without the evaluator's output nothing more can be said either.
    assert classify(failed) is FailureClass.WRONG_ANSWER_UNREVIEWED


def test_every_class_has_a_label_and_reviewed_names_are_checked():
    assert set(LABELS) == set(FailureClass)
    assert reviewed("misread_or_miscounted") is FailureClass.MISREAD_OR_MISCOUNTED
    with pytest.raises(ValueError, match="unknown failure class 'typo'"):
        reviewed("typo")


# -- tables over runs --------------------------------------------------------------


def run_data(name, records, **summary):
    base = {
        "tasks": len(records),
        "successes": sum(r["success"] for r in records),
        "mean_tokens": 20000.0,
        "mean_usd": 0.002,
        "mean_seconds": 30.0,
        "mean_steps": 7.0,
        "total_usd": 0.002 * len(records),
    }
    details = {"3": detail(answer("not_found_error"))}
    return RunData(name, {**base, **summary}, records, details)


def three_runs():
    def records(outcomes):
        return [record(task, template, ok) for (task, template), ok in outcomes.items()]

    tasks = [(1, 10), (2, 10), (3, 20), (4, 20)]
    return [
        run_data(
            "r1",
            records(dict(zip(tasks, [True, True, False, False], strict=True))),
            mean_tokens=18000.0,
        ),
        run_data(
            "r2",
            records(dict(zip(tasks, [True, False, False, True], strict=True))),
            mean_tokens=20000.0,
        ),
        run_data(
            "r3",
            records(dict(zip(tasks, [True, True, False, False], strict=True))),
            mean_tokens=25000.0,
        ),
    ]


def test_spread_is_mean_sample_deviation_and_range():
    stats = spread([2.0, 4.0, 6.0])

    assert stats == {"mean": 4.0, "stdev": 2.0, "min": 2.0, "max": 6.0}
    assert spread([5.0])["stdev"] == 0.0


def test_the_runs_table_has_a_column_per_run_then_mean_and_spread():
    text = runs_table(three_runs())

    assert "| | r1 | r2 | r3 | Mean | Std dev | Min-max |" in text
    assert "| Success | 2/4 | 2/4 | 2/4 | 2.0 | 0.0 | 2-2 |" in text
    assert "| Tokens per task | 18,000 | 20,000 | 25,000 | 21,000 | 3,606 | 18,000-25,000 |" in text


def test_success_per_template_is_out_of_tasks_times_runs():
    rows = template_success(three_runs())

    assert rows == [
        {"template_id": 10, "successes": 5, "attempts": 6, "per_run": [2, 1, 2]},
        {"template_id": 20, "successes": 1, "attempts": 6, "per_run": [0, 1, 0]},
    ]
    text = template_table(three_runs(), {10: "Show the order", 20: "Count the reviews"})
    assert "| 10 | 5/6 | 2, 1, 2 | Show the order |" in text


def test_tasks_that_failed_in_two_of_three_runs_are_listed_with_their_class():
    failures = repeated_failures(three_runs())

    # Task 2 failed once and is left out; 3 failed every time, 4 twice.
    assert [(f["task_id"], f["failures"], f["runs"]) for f in failures] == [(3, 3, 3), (4, 2, 3)]
    assert failures[0]["classes"] == ["gave_up"] * 3
    assert failures[1]["classes"] == ["wrong_answer_unreviewed"] * 2
    assert repeated_failures(three_runs(), at_least=3)[0]["task_id"] == 3


def test_reviewed_labels_replace_the_automatic_class_in_the_table():
    failures = repeated_failures(three_runs())
    labels = {"4": {"class": "misread_or_miscounted", "cause": "counted 7 rows, there are 8"}}

    text = failures_table(failures, labels)

    assert "**Gave up or reported not found** (1)" in text
    assert "| 3 | 20 | 3/3 | not reviewed |" in text
    assert "**Misread or miscounted** (1)" in text
    assert "| 4 | 20 | 2/3 | counted 7 rows, there are 8 |" in text
    assert "Wrong answer, trace not reviewed" not in text


def test_a_run_directory_is_loaded_with_its_evaluator_output(tmp_path):
    run_dir = tmp_path / "2026-11-16_baseline_test_r1"
    (run_dir / "traces" / "3").mkdir(parents=True)
    (run_dir / "records.jsonl").write_text(json.dumps(record(3, 20, False)) + "\n", "utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"tasks": 1, "successes": 0}), "utf-8")
    (run_dir / "traces" / "3" / "eval_result.json").write_text(
        json.dumps(detail(answer("not_found_error"))), "utf-8"
    )

    run = load_run(run_dir)

    assert run.name == "2026-11-16_baseline_test_r1"
    assert classify(run.records[0], run.eval_details["3"]) is FailureClass.GAVE_UP
