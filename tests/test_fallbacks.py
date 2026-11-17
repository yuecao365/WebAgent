"""The fallback ledger, computed from event logs.

Most logs here are synthetic: the real loop is run against scripted replies and a
scripted executor, and the ledger reads the log it wrote. One log is a saved one
from a real run (version 1, a task the harness could not finish).
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from browser_agent.eval.fallbacks import (
    KINDS,
    NOTE,
    TaskLog,
    build_ledger,
    ledger_markdown,
    log_version,
    merge_ledgers,
    run_ledger,
    task_fallbacks,
)
from browser_agent.harness.events import EventLog, read_events
from browser_agent.harness.llm import ModelError, ToolCall, TransientModelError
from browser_agent.harness.loop import AgentLoop, Budgets, LoopConfig
from browser_agent.harness.tools import ToolOutcome

from fakes import FINISH_OK, FIXTURES, FakeExecutor, call, failed, make_client, navigated, reply

CUT_PAGE = "table\n row: 1 | Ann\n … 180 more rows not shown (200 in all). read_page with find"


def events_of(tmp_path, replies, executor=None, config=None, **client):
    llm, _, _, _ = make_client(tmp_path, replies, **client)
    log = EventLog()
    AgentLoop(llm, executor or FakeExecutor(), log, config or LoopConfig()).run("Find it")
    return log.events


def fired(events):
    """(kind, recovered) for every trigger, in log order."""
    return [(item.key, item.recovered) for item in task_fallbacks(events)]


def scored(events, success=True, unexpected_writes=0):
    log = EventLog()
    log.events = list(events)
    log.append("task_scored", success=success, score=float(success), eval_status="ok",
               unexpected_writes=unexpected_writes)  # fmt: skip
    return log.events


FINISH = reply(call("finish", **FINISH_OK))


def test_a_plain_task_fires_nothing(tmp_path):
    events = events_of(tmp_path, [reply(call("click", ref=1)), FINISH])

    assert fired(events) == []
    assert log_version(events) == 3


def test_a_nudge_is_recovered_when_the_next_step_calls_a_tool(tmp_path):
    answered = events_of(tmp_path, [reply(text="Thinking."), FINISH])
    ignored = events_of(tmp_path, [reply(text="Thinking."), reply(text="Still."), FINISH])

    assert fired(answered) == [("nudge", True)]
    assert fired(ignored) == [("nudge", False), ("nudge", True)]


def test_arguments_that_are_not_json_and_what_followed(tmp_path):
    broken = ToolCall("call_x", "click", None, "{ref: 5")
    events = events_of(tmp_path, [reply(broken), reply(call("click", ref=5)), FINISH])

    assert fired(events) == [("bad_arguments", True)]


def test_an_invalid_finish_and_rejected_arguments_are_told_apart(tmp_path):
    bad_finish = {**FINISH_OK, "status": "DONE"}
    executor = FakeExecutor([ToolOutcome(False, "Invalid arguments for click: ref: required")])
    events = events_of(
        tmp_path,
        [reply(call("click")), reply(call("finish", **bad_finish)), FINISH],
        executor=executor,
    )

    # The rejected click was followed by a finish that was rejected too.
    assert fired(events) == [("invalid_arguments", False), ("invalid_finish", True)]


def test_failed_calls_and_the_return_to_a_stable_page(tmp_path):
    config = LoopConfig(failure_limit=2, repeat_limit=99, unchanged_limit=99)
    events = events_of(
        tmp_path,
        [reply(call("click", ref=9)), reply(call("click", ref=8)), FINISH],
        executor=FakeExecutor([failed(), failed()]),
        config=config,
    )

    assert fired(events) == [("tool_error", False), ("tool_error", True), ("recovery", True)]


def test_skipped_calls_are_counted_by_reason(tmp_path):
    two = reply(call("click", ref=1), call("click", ref=2))
    single = events_of(tmp_path, [two, FINISH])
    several = LoopConfig(multi_action=True)
    after_failure = events_of(tmp_path / "b", [two, FINISH], FakeExecutor([failed()]), several)
    after_navigation = events_of(
        tmp_path / "c", [two, FINISH], FakeExecutor([navigated()]), several
    )

    assert fired(single) == [("skipped_single_action", None)]
    assert fired(after_failure) == [("tool_error", True), ("skipped_after_failure", None)]
    assert fired(after_navigation) == [("skipped_after_navigation", None)]


def test_stuck_hints_and_a_task_ended_as_stuck(tmp_path):
    config = LoopConfig(repeat_limit=2, max_stuck_hints=1, unchanged_limit=99)
    same = [reply(call("click", ref=5)) for _ in range(4)]
    ended = events_of(tmp_path, [*same, FINISH], config=config)
    moved_on = events_of(
        tmp_path / "b", [*same[:2], reply(call("click", ref=6)), FINISH], config=config
    )

    # The second time there is no hint: the task is ended and asked for its answer.
    assert fired(ended) == [("stuck_hint", False), ("ended_stuck", True)]
    assert fired(moved_on) == [("stuck_hint", True)]


def test_a_forced_finish_is_recovered_when_it_gives_an_answer(tmp_path):
    config = LoopConfig(budgets=Budgets(max_steps=1))
    click = reply(call("click", ref=1))
    answered = events_of(tmp_path, [click, FINISH], config=config)
    silent = events_of(tmp_path / "b", [click, reply(text="No.")], config=config)

    assert fired(answered) == [("forced_finish", True)]
    assert fired(silent) == [("forced_finish", False), ("no_answer", None)]


def test_model_retries_that_went_through_and_ones_that_did_not(tmp_path):
    busy = TransientModelError("rate limited")
    through = events_of(tmp_path, [busy, busy, FINISH])
    gave_up = events_of(tmp_path / "b", [busy, busy, busy], max_retries=2)
    rejected = events_of(tmp_path / "c", [ModelError("request rejected (400)")])

    assert fired(through) == [("model_retry", True), ("model_retry", True)]
    retried = next(e for e in through if e["type"] == "model_call")
    assert retried["attempts"] == 3
    assert retried["retry_errors"] == ["rate limited", "rate limited"]
    assert fired(gave_up) == [
        ("model_retry", False),
        ("model_retry", False),
        ("model_error", None),
        ("no_answer", None),
    ]
    assert fired(rejected) == [("model_error", None), ("no_answer", None)]


def test_provider_downgrades_reach_the_log(tmp_path):
    downgraded = replace(
        reply(call("click", ref=1)),
        fallbacks=("effort_downgraded: low -> none", "minimal_mode"),
    )
    events = events_of(tmp_path, [downgraded, FINISH])

    logged = [e for e in events if e["type"] == "provider_fallback"]
    assert [(e["fallback"], e["detail"]) for e in logged] == [
        ("effort_downgraded", "low -> none"),
        ("minimal_mode", ""),
    ]
    assert fired(events) == [("effort_downgraded", None), ("minimal_mode", None)]


def test_a_cut_list_and_the_read_that_follows_it(tmp_path):
    found = ToolOutcome(True, "1 lines contain '302':", detail="1 lines contain '302':\nrow")
    missing = ToolOutcome(True, "No line of the page contains '999'.")
    events = events_of(
        tmp_path,
        [
            reply(call("read_page", section=None, find="302")),
            reply(call("read_page", section=None, find="999")),
            reply(call("read_page", section=None, find=None)),
            FINISH,
        ],
        executor=FakeExecutor([found, missing, ToolOutcome(True, "Read the page again.")]),
        config=LoopConfig(unchanged_limit=99),
    )
    # FakeExecutor shows "page <name>"; swap in a page with a cut list at every step.
    for event in events:
        if event["type"] == "observation":
            event["text"] = CUT_PAGE

    assert fired(events) == [
        ("cut_list_shown", None),
        ("cut_list_read", True),
        ("cut_list_shown", None),
        ("cut_list_read", False),
        # Reading the whole page again is not a look into the cut part.
        ("cut_list_shown", None),
        ("cut_list_shown", None),
    ]


def test_results_that_tell_of_a_fallback_inside_a_tool(tmp_path):
    outcomes = [
        ToolOutcome(True, "Clicked [4] by script because it has no visible box.", acted=True),
        ToolOutcome(True, "Clicked [5]. Dialog accepted: confirm: Delete?", acted=True),
        ToolOutcome(False, "type failed: " + "x" * 50 + "… [900 more characters]", acted=True),
    ]
    events = events_of(
        tmp_path,
        [*(reply(call("click", ref=n)) for n in (4, 5, 6)), FINISH],
        FakeExecutor(outcomes),
    )

    assert fired(events) == [
        ("script_click", None),
        ("dialog_accepted", None),
        ("result_cut", None),
        ("tool_error", True),
    ]


def test_events_reported_from_outside_the_loop(tmp_path):
    events = events_of(tmp_path, [reply(call("click", ref=1)), FINISH])
    log = EventLog()
    log.events = list(events[:-1])
    log.append("page_read_retry", retries=2, ok=True, error="timed out")
    log.append("settle_timeout", seconds=30.0)
    log.events.append(events[-1])

    assert fired(scored(log.events, unexpected_writes=1)) == [
        ("page_read_retry", True),
        ("page_read_retry", True),
        ("settle_timeout", None),
        ("unexpected_write", None),
    ]


class TabOpeningExecutor(FakeExecutor):
    """Reports a new tab on every click, as the real executor does through notify."""

    def __init__(self, log):
        super().__init__()
        self.log = log

    def execute(self, name, arguments):
        if name == "click":
            self.log.append("new_tab", url="http://site.test/admin/catalog/product/edit/id/7/")
        return super().execute(name, arguments)


def test_a_new_tab_is_counted_and_recovered_when_the_next_step_works(tmp_path):
    llm, _, _, _ = make_client(tmp_path, [reply(call("click", ref=1)), FINISH])
    log = EventLog()
    AgentLoop(llm, TabOpeningExecutor(log), log, LoopConfig()).run("Find it")

    assert fired(log.events) == [("new_tab", True)]
    assert build_ledger([TaskLog(1, log.events)])["rows"]["new_tab"]["logged"]


def test_a_log_older_than_a_kind_reports_it_as_not_logged_not_as_zero(tmp_path):
    """baseline_test_r1 and r2 are version 2: they could not have recorded a new tab."""
    events = [
        {**event, "log_version": 2} if event["type"] == "task_start" else event
        for event in events_of(tmp_path, [FINISH])
    ]

    ledger = build_ledger([TaskLog(1, events)])

    assert not ledger["rows"]["new_tab"]["logged"]
    assert ledger["rows"]["settle_timeout"]["logged"]
    not_logged = ledger_markdown(ledger).split("Not logged in this run")[1]
    assert "New tab opened by an action, closed" in not_logged


def test_the_check_before_a_task_leaves_its_repairs_and_restarts_in_the_ledger(tmp_path):
    ran = events_of(tmp_path, [FINISH])
    log = EventLog()
    log.append("env_repaired", problems=["1 extra tab(s) open: about:blank"])
    log.append("browser_restarted", reason="the agent's tab stays hidden", problems=[])
    log.events += ran
    never_started = EventLog()
    never_started.append("browser_restarted", reason="the agent's tab no longer exists")
    never_started.append("harness_error", error="EnvironmentFault: ...", log_version=3)

    assert fired(log.events) == [("env_repaired", None), ("browser_restarted", True)]
    assert fired(never_started.events) == [("browser_restarted", False), ("harness_error", None)]
    assert log_version(never_started.events) == 3


def test_a_saved_version_1_log_of_a_task_the_harness_could_not_finish():
    events = read_events(FIXTURES / "events_v1_harness_error.jsonl")

    assert log_version(events) == 1
    # The last click failed and nothing came after it: no task_end was written.
    assert fired(events) == [("tool_error", False), ("harness_error", None)]


def test_a_logged_harness_error_is_counted_once(tmp_path):
    log = EventLog.resume(tmp_path / "traces" / "7" / "events.jsonl")
    log.append("harness_error", error="BrowserError: gone")

    assert fired(read_events(log.path)) == [("harness_error", None)]


def test_the_ledger_counts_triggers_tasks_recoveries_and_scores(tmp_path):
    nudged = scored(events_of(tmp_path, [reply(text="Hm."), reply(text="Hm."), FINISH]), True)
    nudged_and_failed = scored(events_of(tmp_path / "b", [reply(text="Hm."), FINISH]), False)
    plain = scored(events_of(tmp_path / "c", [FINISH]), True)

    ledger = build_ledger(
        TaskLog(n, events) for n, events in enumerate([nudged, nudged_and_failed, plain])
    )

    assert (ledger["tasks"], ledger["task_successes"]) == (3, 2)
    row = ledger["rows"]["nudge"]
    assert (row["triggers"], row["tasks"], row["recovered"], row["task_successes"]) == (3, 2, 2, 1)
    # Where "recovered" has no meaning it is None, not zero.
    assert ledger["rows"]["settle_timeout"]["recovered"] is None
    assert set(ledger["rows"]) == {kind.key for kind in KINDS}


def test_old_logs_take_the_score_from_the_records_and_mark_what_was_not_logged():
    events = read_events(FIXTURES / "events_v1_harness_error.jsonl")

    ledger = build_ledger([TaskLog(486, events, recorded_success=False)])
    again = build_ledger(
        [TaskLog(486, events, recorded_success=True, recorded_unexpected_writes=2)]
    )

    assert ledger["task_successes"] == 0
    assert again["task_successes"] == 1
    assert again["rows"]["unexpected_write"]["triggers"] == 1
    assert not ledger["rows"]["page_read_retry"]["logged"]
    assert ledger["rows"]["tool_error"]["logged"]
    text = ledger_markdown(ledger)
    assert "Not logged in this run (older log version): " in text
    assert "Page read retried: page busy" in text.split("Not logged in this run")[1]


def test_the_table_lists_what_fired_and_says_what_the_last_column_is_not(tmp_path):
    events = scored(events_of(tmp_path, [reply(text="Hm."), FINISH]), True)

    text = ledger_markdown(build_ledger([TaskLog(1, events)]))

    assert "| Reply without a tool call, nudged | 1 | 1 | 1/1 | 1/1 |" in text
    assert NOTE in text
    assert "a correlation, not a rescue rate" in text
    assert "Did not fire: " in text
    assert "| Settle ran out of time" not in text


def test_ledgers_of_several_runs_add_up(tmp_path):
    first = build_ledger([TaskLog(1, scored(events_of(tmp_path, [reply(text="Hm."), FINISH])))])
    second = build_ledger(
        [TaskLog(1, scored(events_of(tmp_path / "b", [reply(text="Hm."), FINISH]), False))]
    )

    total = merge_ledgers([first, second])

    assert (total["tasks"], total["task_successes"]) == (2, 1)
    row = total["rows"]["nudge"]
    assert (row["triggers"], row["tasks"], row["recovered"], row["task_successes"]) == (2, 2, 2, 1)


def test_a_run_directory_is_read_back_from_its_traces(tmp_path):
    run_dir = tmp_path / "2026-11-16_demo"
    new = scored(events_of(tmp_path, [reply(text="Hm."), FINISH]), True)
    old = read_events(FIXTURES / "events_v1_harness_error.jsonl")
    for task_id, events in ((101, new), (486, old)):
        path = run_dir / "traces" / str(task_id) / "events.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    (run_dir / "records.jsonl").write_text(
        json.dumps({"task_id": 486, "success": False, "unexpected_writes": []}) + "\n",
        encoding="utf-8",
    )

    ledger = run_ledger(run_dir)

    assert (ledger["tasks"], ledger["task_successes"]) == (2, 1)
    assert ledger["rows"]["nudge"]["triggers"] == 1
    assert ledger["rows"]["harness_error"]["tasks"] == 1


@pytest.mark.parametrize("kind", KINDS, ids=lambda kind: kind.key)
def test_every_kind_has_a_label_and_says_what_recovered_means(kind):
    assert kind.label
    assert kind.recovered is None or len(kind.recovered) > 5


def test_the_check_before_finishing_has_its_own_numbers(tmp_path):
    checking = LoopConfig(verify_before_finish=True)
    other = reply(call("finish", **{**FINISH_OK, "retrieved_data": '["43"]'}))
    look = reply(call("read_page", section=None, find="x"))
    changed = scored(events_of(tmp_path, [FINISH, look, other], config=checking), True)
    same = scored(events_of(tmp_path / "b", [FINISH, FINISH], config=checking), False)
    off = scored(events_of(tmp_path / "c", [FINISH]), True)

    ledger = build_ledger(TaskLog(n, events) for n, events in enumerate([changed, same, off]))

    assert ledger["self_check"] == {
        "triggered": 2,
        "answer_changed": 1,
        "extra_steps": 3,
        "task_successes": 1,
    }
    row = ledger["rows"]["self_check"]
    assert (row["triggers"], row["tasks"], row["recovered"], row["task_successes"]) == (2, 2, 1, 1)
    text = ledger_markdown(ledger)
    assert "Check before finishing: triggered in 2 tasks, answer changed in 1, 3 extra" in text
