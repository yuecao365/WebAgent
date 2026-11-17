"""The fallback ledger: how often each fallback of the harness fired, and what followed.

A fallback is anything the harness does when a step does not go the plain way: it
returns an error to the model, asks again, skips, waits, retries, downgrades or ends
the task early. The ledger is computed from the event logs alone, so it can be
rebuilt for any run whose traces are on disk.

For every kind of fallback the ledger gives:

triggers
    How many times it fired, over all tasks.
tasks
    In how many tasks it fired at least once.
recovered
    Of the triggers, how many were followed by what the fallback was for. It is only
    given where that question has an answer; each kind below says what it counts.
    "The next step succeeded" means: the model call after the trigger made at least
    one tool call, and every call of it that ran came back without an error.
task successes
    Of the tasks it fired in, how many the evaluator scored successful.

"Task successes" is a correlation, not a rescue rate. A fallback can fire in a task
that succeeds for other reasons, and one that worked perfectly can sit in a task
that fails later for an unrelated reason. Only "recovered" says something about the
fallback itself, and only about the step right after it.

The score comes from the task_scored event. Logs written before that event existed
(log version 1) take it from the run's records.jsonl instead. A kind that left no
event in the log version of a run is reported as "not logged" for that run, never as
zero: several kinds are logged since version 2, new tabs and the environment check
since version 3.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from browser_agent.harness.events import read_events

NEXT_STEP = "the next step succeeded"


@dataclass(frozen=True)
class Kind:
    """One kind of fallback: its name in the ledger and what "recovered" means for it."""

    key: str
    label: str
    # What counts as recovered, or None where the question does not apply.
    recovered: str | None = None
    # The first log version in which this kind leaves an event.
    since: int = 1


KINDS: tuple[Kind, ...] = (
    # -- what the model sent could not be used --------------------------------
    Kind("bad_arguments", "Tool arguments not JSON, error returned", NEXT_STEP),
    Kind("invalid_arguments", "Arguments rejected by the schema, or unknown tool", NEXT_STEP),
    Kind("invalid_finish", "Invalid finish returned to the model", NEXT_STEP),
    Kind("nudge", "Reply without a tool call, nudged", NEXT_STEP),
    Kind("skipped_single_action", "Extra call skipped: one call per step"),
    Kind("skipped_after_failure", "Call skipped after a failed call", since=2),
    Kind("skipped_after_navigation", "Call skipped after a new page", since=2),
    # -- a tool call failed -----------------------------------------------------
    Kind("tool_error", "Tool call failed, error returned", NEXT_STEP),
    Kind("recovery", "Returned to the last stable URL", f"the return worked and {NEXT_STEP}"),
    Kind("script_click", "Clicked by script: element has no box"),
    Kind("dialog_accepted", "Native dialog accepted"),
    Kind("result_cut", "Long tool result cut"),
    Kind("new_tab", "New tab opened by an action, closed", NEXT_STEP, 3),
    # -- the page ---------------------------------------------------------------
    Kind("page_read_retry", "Page read retried: page busy", "the page was read", 2),
    Kind("settle_timeout", "Settle ran out of time", since=2),
    Kind("cut_list_shown", "Page shown with a cut list or table"),
    Kind(
        "cut_list_read",
        "Cut list followed by read_page(find/section)",
        "the read returned lines",
    ),
    # -- the loop ---------------------------------------------------------------
    Kind("stuck_hint", "Stuck hint given", "the task did not end as stuck"),
    Kind("ended_stuck", "Task ended as stuck (forced finish)", "an answer was given"),
    Kind("forced_finish", "Forced finish on a budget", "an answer was given"),
    Kind("no_answer", "Task ended without an answer"),
    Kind(
        "self_check",
        "Finish intercepted for a check",
        "the answer changed between the first and the second finish",
        2,
    ),
    # -- the model API ------------------------------------------------------------
    Kind("model_retry", "Model API call retried (429, 5xx, timeout)", "the call went through"),
    Kind("effort_downgraded", "Reasoning effort rejected, downgraded", None, 2),
    Kind("minimal_mode", "Switched to minimal request mode", None, 2),
    Kind("model_error", "Task ended by a model error"),
    Kind("model_refusal", "Task ended by a model refusal"),
    Kind("spend_cap", "Task ended by the spend cap"),
    # -- the run ------------------------------------------------------------------
    Kind("unexpected_write", "Read-only task wrote; next task reset first", None, 2),
    Kind("harness_error", "Harness error ended the task"),
)

_BY_KEY = {kind.key: kind for kind in KINDS}

_CUT_LIST = re.compile(r"… \d+ more \w+ not shown")
_CUT_RESULT = re.compile(r"… \[\d+ more characters\]$")
_NOT_JSON = "The arguments were not a JSON object"
_REJECTED = ("Invalid arguments for ", "Unknown tool ")


@dataclass(frozen=True)
class Fired:
    """One trigger of a fallback in one task."""

    key: str
    step: int
    recovered: bool | None = None


@dataclass
class _Step:
    index: int
    observation: dict[str, Any] | None = None
    model_call: dict[str, Any] | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    others: list[dict[str, Any]] = field(default_factory=list)

    def succeeded(self) -> bool:
        return bool(self.results) and all(result.get("ok") for result in self.results)


def _steps(events: Sequence[dict[str, Any]]) -> list[_Step]:
    """Group a log into steps. Step 0 holds what happened before the first one."""
    steps = [_Step(0)]
    for event in events:
        kind = event["type"]
        if kind == "observation":
            steps.append(_Step(len(steps), observation=event))
        elif kind == "model_call":
            if steps[-1].model_call is not None or steps[-1].observation is None:
                steps.append(_Step(len(steps)))
            steps[-1].model_call = event
        elif kind == "tool_call":
            steps[-1].calls.append(event)
        elif kind == "tool_result":
            steps[-1].results.append(event)
        else:
            steps[-1].others.append(event)
    return steps


def log_version(events: Sequence[dict[str, Any]]) -> int:
    # task_start carries it; so does the harness_error of a task that never started.
    stamped = next((event for event in events if "log_version" in event), {})
    return int(stamped.get("log_version", 1))


def task_success(events: Sequence[dict[str, Any]]) -> bool | None:
    """The evaluator's verdict as logged, or None when the log does not hold it."""
    scored = next((event for event in events if event["type"] == "task_scored"), None)
    return None if scored is None else bool(scored.get("success"))


def self_check_details(events: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """What the check before finishing did in this task, or None if it did not run."""
    check = next((event for event in events if event["type"] == "self_check"), None)
    if check is None:
        return None
    end = next((event for event in events if event["type"] == "task_end"), {})
    last_step = max(
        (event.get("step", 0) for event in events if event["type"] == "model_call"), default=0
    )
    second = end.get("response")
    return {
        "first": check.get("first"),
        "second": second,
        # A task that ran out of budget during the check has no second answer.
        "changed": second is not None and second != check.get("first"),
        "extra_steps": max(last_step - int(check.get("step", last_step)), 0),
    }


def task_fallbacks(events: Sequence[dict[str, Any]]) -> list[Fired]:
    """Every fallback that fired in one task, in log order."""
    fired: list[Fired] = []
    steps = _steps(events)
    end = next((event for event in events if event["type"] == "task_end"), None)
    answered = end is not None and end.get("response") is not None
    ended_stuck = end is not None and end.get("reason") == "stuck"

    for position, step in enumerate(steps):
        following = steps[position + 1] if position + 1 < len(steps) else None
        next_ok = following is not None and following.succeeded()

        def add(key: str, recovered: bool | None = None, at: int = step.index) -> None:
            fired.append(Fired(key, at, recovered))

        page = (step.observation or {}).get("text", "")
        cut = bool(_CUT_LIST.search(page))
        if cut:
            add("cut_list_shown")

        for call in step.calls:
            if "arguments" in call and call["arguments"] is None:
                add("bad_arguments", next_ok)
        for call, result in zip(step.calls, step.results, strict=False):
            content = result.get("content") or ""
            arguments = call.get("arguments") or {}
            if cut and call.get("name") == "read_page" and isinstance(arguments, dict):
                asked = (arguments.get("find") or "").strip() or arguments.get("section")
                if asked:
                    add("cut_list_read", bool(result.get("ok")) and not content.startswith("No "))
            if "by script because" in content:
                add("script_click")
            if "Dialog accepted:" in content:
                add("dialog_accepted")
            if _CUT_RESULT.search(content):
                add("result_cut")
            if result.get("ok"):
                continue
            if content.startswith(_NOT_JSON):
                continue  # counted above, from the call
            if result.get("name") == "finish":
                add("invalid_finish", next_ok)
            elif content.startswith(_REJECTED):
                add("invalid_arguments", next_ok)
            else:
                add("tool_error", next_ok)

        model_call = step.model_call or {}
        retries = int(model_call.get("attempts", 1)) - 1
        for _ in range(max(retries, 0)):
            add("model_retry", True)

        for place, event in enumerate(step.others):
            kind = event["type"]
            if kind == "nudge":
                add("nudge", next_ok)
            elif kind == "tool_skipped":
                add(f"skipped_{event.get('reason', 'single_action')}")
            elif kind == "stuck":
                after = step.others[place + 1] if place + 1 < len(step.others) else {}
                if after.get("type") == "budget" and after.get("detail") == "stuck":
                    continue  # no hint this time: the task was ended instead
                add("stuck_hint", not ended_stuck)
            elif kind == "recovery":
                add("recovery", bool(event.get("ok")) and next_ok)
            elif kind == "budget":
                key = "ended_stuck" if event.get("detail") == "stuck" else "forced_finish"
                add(key, answered)
            elif kind == "page_read_retry":
                for _ in range(max(int(event.get("retries", 1)), 1)):
                    add("page_read_retry", bool(event.get("ok")))
            elif kind == "settle_timeout":
                add("settle_timeout")
            elif kind == "new_tab":
                add("new_tab", next_ok)
            elif kind == "provider_fallback":
                if event.get("fallback") in _BY_KEY:
                    add(event["fallback"])
            elif kind == "model_error":
                for _ in range(max(int(event.get("attempts", 1)) - 1, 0)):
                    add("model_retry", False)
            elif kind == "self_check":
                details = self_check_details(events) or {}
                add("self_check", bool(details.get("changed")))
            elif kind == "task_scored":
                if event.get("unexpected_writes"):
                    add("unexpected_write")
            elif kind == "harness_error":
                add("harness_error")

    last = steps[-1].index
    if end is None:
        # The loop never reached its end: the harness failed underneath it.
        if not any(item.key == "harness_error" for item in fired):
            fired.append(Fired("harness_error", last))
    else:
        if end.get("reason") in ("model_error", "model_refusal", "spend_cap"):
            fired.append(Fired(end["reason"], last))
        if not answered:
            fired.append(Fired("no_answer", last))
    return fired


@dataclass(frozen=True)
class TaskLog:
    """The events of one task and, for old logs, the score kept beside them."""

    task_id: int | str
    events: Sequence[dict[str, Any]]
    # Used only when the log itself holds no task_scored event.
    recorded_success: bool | None = None
    recorded_unexpected_writes: int = 0

    def success(self) -> bool:
        logged = task_success(self.events)
        return bool(self.recorded_success) if logged is None else logged


def build_ledger(tasks: Iterable[TaskLog]) -> dict[str, Any]:
    """The ledger of a set of tasks; see the module docstring for what the columns mean."""
    rows = {
        kind.key: {
            "label": kind.label,
            "triggers": 0,
            "tasks": 0,
            "recovered": 0 if kind.recovered else None,
            "recovered_means": kind.recovered,
            "task_successes": 0,
            "logged": True,
        }
        for kind in KINDS
    }
    self_check = {"triggered": 0, "answer_changed": 0, "extra_steps": 0, "task_successes": 0}
    count = successes = 0
    for task in tasks:
        count += 1
        success = task.success()
        successes += success
        fired = task_fallbacks(task.events)
        if task_success(task.events) is None and task.recorded_unexpected_writes:
            fired.append(Fired("unexpected_write", 0))
        version = log_version(task.events)
        for kind in KINDS:
            # An old log's unexpected writes are taken from the records instead.
            if kind.since > version and kind.key != "unexpected_write":
                rows[kind.key]["logged"] = False
        for key in {item.key for item in fired}:
            rows[key]["tasks"] += 1
            rows[key]["task_successes"] += success
        for item in fired:
            row = rows[item.key]
            row["triggers"] += 1
            if row["recovered"] is not None and item.recovered:
                row["recovered"] += 1
        details = self_check_details(task.events)
        if details is not None:
            self_check["triggered"] += 1
            self_check["answer_changed"] += bool(details["changed"])
            self_check["extra_steps"] += details["extra_steps"]
            self_check["task_successes"] += success
    return {
        "tasks": count,
        "task_successes": successes,
        "rows": rows,
        "self_check": self_check,
    }


def merge_ledgers(ledgers: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Sum the ledgers of several runs. A task run twice counts as two tasks."""
    merged = build_ledger([])
    for ledger in ledgers:
        merged["tasks"] += ledger["tasks"]
        merged["task_successes"] += ledger["task_successes"]
        for key, row in ledger["rows"].items():
            into = merged["rows"][key]
            for name in ("triggers", "tasks", "task_successes"):
                into[name] += row[name]
            if into["recovered"] is not None and row["recovered"] is not None:
                into["recovered"] += row["recovered"]
            into["logged"] = into["logged"] and row.get("logged", True)
        for name, value in ledger.get("self_check", {}).items():
            merged["self_check"][name] += value
    return merged


def run_ledger(run_dir: Path) -> dict[str, Any]:
    """Rebuild the ledger of a run from the event logs under its traces directory."""
    records: dict[str, dict[str, Any]] = {}
    records_path = run_dir / "records.jsonl"
    if records_path.exists():
        with records_path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    record = json.loads(line)
                    records[str(record["task_id"])] = record
    tasks = []
    for log in sorted((run_dir / "traces").glob("*/events.jsonl")):
        record = records.get(log.parent.name, {})
        tasks.append(
            TaskLog(
                task_id=log.parent.name,
                events=read_events(log),
                recorded_success=record.get("success"),
                recorded_unexpected_writes=len(record.get("unexpected_writes") or []),
            )
        )
    return build_ledger(tasks)


NOTE = (
    "Recovered counts triggers that were followed by what the fallback was for; it is "
    "given only where that applies. Tasks successful is a correlation, not a rescue "
    "rate: a fallback can fire in a task that succeeds for other reasons."
)


def ledger_markdown(ledger: dict[str, Any]) -> str:
    """The ledger as a table of the kinds that fired, with the rest listed below it."""
    lines = [
        f"Tasks: {ledger['tasks']}, of which {ledger['task_successes']} scored successful.",
        "",
        "| Fallback | Triggers | Tasks | Recovered | Tasks successful |",
        "|---|---:|---:|---:|---:|",
    ]
    quiet: list[str] = []
    unlogged: list[str] = []
    for row in ledger["rows"].values():
        if not row["triggers"]:
            (quiet if row.get("logged", True) else unlogged).append(row["label"])
            continue
        recovered = "n/a" if row["recovered"] is None else f"{row['recovered']}/{row['triggers']}"
        lines.append(
            f"| {row['label']} | {row['triggers']} | {row['tasks']} | {recovered} | "
            f"{row['task_successes']}/{row['tasks']} |"
        )
    lines += ["", NOTE]
    check = ledger.get("self_check", {})
    if check.get("triggered"):
        lines += [
            "",
            f"Check before finishing: triggered in {check['triggered']} tasks, answer changed "
            f"in {check['answer_changed']}, {check['extra_steps']} extra steps, "
            f"{check['task_successes']} of those tasks scored successful.",
        ]
    if quiet:
        lines += ["", "Did not fire: " + "; ".join(quiet) + "."]
    if unlogged:
        lines += ["", "Not logged in this run (older log version): " + "; ".join(unlogged) + "."]
    return "\n".join(lines) + "\n"
