"""Rough classes of failed tasks: the start of the failure taxonomy.

A failed task gets one class. Some classes can be told from the record and the
evaluator's output alone; the others need someone to read the trace, because a wrong
answer looks the same whether the agent was on the wrong page, misread the right
one, or the page never showed what was asked. `classify` gives the class it can
establish and says so when it cannot; a reviewed label, when there is one, replaces
it.

This runs after scoring, for analysis. Nothing here is shown to the agent.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any


class FailureClass(StrEnum):
    WRONG_PAGE_OR_FILTER = "wrong_page_or_filter"
    MISREAD_OR_MISCOUNTED = "misread_or_miscounted"
    ACTION_NOT_DONE = "action_not_done"
    GAVE_UP = "gave_up"
    NOT_ON_PAGE = "not_on_page"
    OVER_BUDGET = "over_budget"
    HARNESS_ERROR = "harness_error"
    # A wrong answer whose trace nobody has read yet.
    WRONG_ANSWER_UNREVIEWED = "wrong_answer_unreviewed"


LABELS: dict[FailureClass, str] = {
    FailureClass.WRONG_PAGE_OR_FILTER: "Wrong page or filter",
    FailureClass.MISREAD_OR_MISCOUNTED: "Misread or miscounted",
    FailureClass.ACTION_NOT_DONE: "Action not done or done wrongly",
    FailureClass.GAVE_UP: "Gave up or reported not found",
    FailureClass.NOT_ON_PAGE: "The page does not show the information",
    FailureClass.OVER_BUDGET: "Ran out of budget, stuck, or the model call failed",
    FailureClass.HARNESS_ERROR: "Harness error",
    FailureClass.WRONG_ANSWER_UNREVIEWED: "Wrong answer, trace not reviewed",
}

# Classes that only a reading of the trace can establish.
NEEDS_REVIEW = frozenset(
    {
        FailureClass.WRONG_PAGE_OR_FILTER,
        FailureClass.MISREAD_OR_MISCOUNTED,
        FailureClass.NOT_ON_PAGE,
    }
)

_ENDED_EARLY = ("budget_", "stuck", "model_error", "model_refusal", "spend_cap")


def _status(value: Any) -> str:
    return str(value or "").strip().lower()


def classify(
    record: Mapping[str, Any], eval_detail: Mapping[str, Any] | None = None
) -> FailureClass | None:
    """The class of a failed task as far as its record and the evaluator show it.

    None for a successful task. A wrong answer comes back as WRONG_ANSWER_UNREVIEWED:
    which of the three reviewed classes it is cannot be told from here.
    """
    if record.get("success"):
        return None
    reason = str(record.get("finish_reason", ""))
    if reason == "harness_error":
        return FailureClass.HARNESS_ERROR
    if reason.startswith(_ENDED_EARLY):
        return FailureClass.OVER_BUDGET

    results = {
        result.get("evaluator_name"): result
        for result in (eval_detail or {}).get("evaluators_results") or []
    }
    answer = results.get("AgentResponseEvaluator") or {}
    actual = _status((answer.get("actual_normalized") or answer.get("actual") or {}).get("status"))
    expected = _status((answer.get("expected") or {}).get("status"))
    if expected == "success" and actual and actual != "success":
        return FailureClass.GAVE_UP
    others_failed = any(
        _status(result.get("status")) != "success"
        for name, result in results.items()
        if name != "AgentResponseEvaluator"
    )
    if others_failed and _status(answer.get("status")) in ("success", ""):
        # The answer was accepted; what the task was to do on the site was not found.
        return FailureClass.ACTION_NOT_DONE
    return FailureClass.WRONG_ANSWER_UNREVIEWED


def reviewed(label: str) -> FailureClass:
    """A class named in a reviewed-labels file; an unknown name is an error."""
    try:
        return FailureClass(label)
    except ValueError:
        known = ", ".join(item.value for item in FailureClass)
        raise ValueError(f"unknown failure class {label!r}; known: {known}") from None
