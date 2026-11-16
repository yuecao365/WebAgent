"""The agent loop with scripted model replies: flow, budgets, stuck detection, recovery."""

from __future__ import annotations

import itertools

import pytest

from browser_agent.harness.events import EventLog
from browser_agent.harness.llm import (
    AssistantMessage,
    ModelError,
    ToolCall,
    ToolMessage,
    Usage,
    UserMessage,
)
from browser_agent.harness.loop import (
    AFTER_FAILURE,
    AFTER_NAVIGATION,
    BAD_ARGUMENTS,
    EMPTY_NOTE,
    EXTRA_CALL,
    NUDGE,
    AgentLoop,
    Budgets,
    LoopConfig,
    system_prompt,
)
from browser_agent.harness.tools import TOOLS, ToolOutcome

from fakes import FINISH_OK, FakeExecutor, call, failed, make_client, navigated, reply


def run(tmp_path, replies, executor=None, config=None, clock=None, budget_usd=100.0):
    client, provider, ledger, _ = make_client(tmp_path, replies, budget_usd=budget_usd)
    executor = executor or FakeExecutor()
    events = EventLog()
    kwargs = {"clock": clock} if clock else {}
    loop = AgentLoop(client, executor, events, config or LoopConfig(), **kwargs)
    result = loop.run("Find the answer")
    return result, provider, executor, events, ledger


def kinds(events):
    return [event["type"] for event in events.events]


def text_of(message):
    return message.text if isinstance(message, AssistantMessage) else message.content


def tail(provider, index):
    """The last message of a request: page, note and status, by section."""
    message = provider.calls[index]["messages"][-1]
    assert isinstance(message, UserMessage)
    return {part.section: part.text for part in message.parts}


def test_acts_then_finishes(tmp_path):
    result, _provider, executor, events, _ = run(
        tmp_path, [reply(call("click", ref=7)), reply(call("finish", **FINISH_OK))]
    )

    assert result.reason == "finished"
    assert not result.forced
    assert result.steps == 2
    assert result.finish.response() == {
        "task_type": "RETRIEVE",
        "status": "SUCCESS",
        "retrieved_data": ["42"],
        "error_details": None,
    }
    assert executor.executed[0] == ("click", {"ref": 7})
    assert kinds(events) == [
        "task_start", "observation", "model_call", "tool_call", "tool_result",
        "observation", "model_call", "tool_call", "tool_result", "task_end",
    ]  # fmt: skip


def test_prompt_is_task_then_history_then_tail(tmp_path):
    _, provider, _, _, _ = run(
        tmp_path, [reply(call("click", ref=7)), reply(call("finish", **FINISH_OK))]
    )
    first, second = (c["messages"] for c in provider.calls)

    assert first[0] == UserMessage("Task: Find the answer", section="task")
    assert len(first) == 2
    assert tail(provider, 0) == {
        "observation": "Current page:\npage p1",
        "notes": f"Working note:\n{EMPTY_NOTE}",
        "status": "Step 1 of 30.",
    }
    # Step 2: the call and its one-line result joined the history; the tail is new.
    assert [type(m) for m in second] == [UserMessage, AssistantMessage, ToolMessage, UserMessage]
    assert second[2].content == "click done."
    assert tail(provider, 1)["observation"] == "Current page:\npage p2"
    assert tail(provider, 1)["status"] == "Step 2 of 30."


def test_pages_never_enter_the_history(tmp_path):
    replies = [reply(call("click", ref=n)) for n in range(5)]
    replies.append(reply(call("finish", **FINISH_OK)))
    _, provider, _, _, _ = run(tmp_path, replies)

    for request in provider.calls:
        *before, last = request["messages"]
        assert "page p" in last.content
        assert not any("page p" in text_of(message) for message in before)


def test_pages_stay_in_the_history_when_asked_for(tmp_path):
    """The full-history arm: what the harness did before the cache-friendly layout."""
    replies = [reply(call("click", ref=n)) for n in range(3)]
    replies.append(reply(call("finish", **FINISH_OK)))
    _, provider, _, _, _ = run(tmp_path, replies, config=LoopConfig(pages_in_history=True))
    requests = [c["messages"] for c in provider.calls]

    # Every earlier page is still there, so the prompt grows by a page per step.
    assert [sum("page p" in text_of(m) for m in messages) for messages in requests] == [1, 2, 3, 4]
    assert "page p4" in requests[3][-1].content
    # Each request is the one before plus the step's call, its result and the new page.
    for earlier, later in itertools.pairwise(requests):
        assert later[: len(earlier)] == earlier
        assert len(later) == len(earlier) + 3
    assert provider.calls[0]["system"] == system_prompt(False, pages_in_history=True)
    assert "stay above in the conversation" in provider.calls[0]["system"]


def test_system_prompt_and_tools_are_the_same_at_every_step(tmp_path):
    replies = [reply(call("click", ref=n)) for n in range(3)]
    replies.append(reply(call("finish", **FINISH_OK)))
    _, provider, _, _, _ = run(tmp_path, replies)

    assert {c["system"] for c in provider.calls} == {system_prompt(multi_action=False)}
    assert {tuple(c["tools"]) for c in provider.calls} == {tuple(t.name for t in TOOLS)}
    # Nothing that counts steps or time may sit in the stable part.
    assert "Step" not in provider.calls[0]["system"]


def test_usage_and_cost_add_up_over_calls(tmp_path):
    usage = Usage(input_tokens=2000, cached_input_tokens=1000, output_tokens=50)
    result, _, _, _, ledger = run(
        tmp_path,
        [reply(call("click", ref=1), usage=usage), reply(call("finish", **FINISH_OK), usage=usage)],
    )

    assert result.usage == usage + usage
    # per call: 2000 * $1 + 1000 * $0.1 + 50 * $10, per million tokens
    assert result.cost_usd == pytest.approx(2 * 0.0026)
    assert ledger.total_usd == pytest.approx(result.cost_usd)


def test_step_budget_forces_a_finish(tmp_path):
    config = LoopConfig(budgets=Budgets(max_steps=2))
    unknown = {**FINISH_OK, "status": "UNKNOWN_ERROR", "error_details": "ran out"}
    replies = [
        reply(call("click", ref=1)),
        reply(call("click", ref=2)),
        reply(call("finish", **unknown)),
    ]
    result, provider, _, events, _ = run(tmp_path, replies, config=config)

    assert result.reason == "budget_steps"
    assert result.forced
    assert result.finish.status == "UNKNOWN_ERROR"
    assert "step budget is used up. Call finish now" in tail(provider, 2)["status"]
    # The tool list is left alone: changing it would throw the cached prompt away.
    assert provider.calls[2]["tools"] == provider.calls[0]["tools"]
    assert events.events[-1]["reason"] == "budget_steps"
    assert "budget" in kinds(events)


def test_forced_finish_ignores_other_calls(tmp_path):
    config = LoopConfig(budgets=Budgets(max_steps=1))
    result, _, executor, _, _ = run(
        tmp_path, [reply(call("click", ref=1)), reply(call("click", ref=2))], config=config
    )

    assert result.reason == "budget_steps"
    assert result.finish is None
    assert result.error == "no finish call after the budget ran out"
    assert executor.executed == [("click", {"ref": 1})]


def test_token_budget(tmp_path):
    config = LoopConfig(budgets=Budgets(max_tokens=1500))
    big = Usage(input_tokens=1400, output_tokens=200)
    result, provider, _, _, _ = run(
        tmp_path,
        [reply(call("click", ref=1), usage=big), reply(call("finish", **FINISH_OK))],
        config=config,
    )

    assert result.reason == "budget_tokens"
    assert len(provider.calls) == 2


def test_time_budget(tmp_path):
    ticks = itertools.count(0, 60)  # every look at the clock is 60 seconds later
    config = LoopConfig(budgets=Budgets(max_seconds=100))
    result, _, _, _, _ = run(
        tmp_path,
        [reply(call("click", ref=1)), reply(call("finish", **FINISH_OK))],
        config=config,
        clock=lambda: next(ticks),
    )

    assert result.reason == "budget_time"


def test_cost_budget(tmp_path):
    config = LoopConfig(budgets=Budgets(max_usd=0.001))
    result, _, _, _, _ = run(
        tmp_path,
        [reply(call("click", ref=1)), reply(call("finish", **FINISH_OK))],
        config=config,
    )

    assert result.reason == "budget_usd"
    assert result.forced


def test_spend_cap_stops_without_another_call(tmp_path):
    result, provider, _, _, ledger = run(tmp_path, [reply(call("click", ref=1))], budget_usd=0.0001)

    assert result.reason == "spend_cap"
    assert provider.calls == []
    assert ledger.total_usd == 0


def test_repeating_the_same_call_gets_a_hint_then_ends_the_task(tmp_path):
    config = LoopConfig(repeat_limit=2, max_stuck_hints=1, unchanged_limit=99)
    replies = [reply(call("click", ref=5)) for _ in range(4)]
    replies.append(reply(call("finish", **FINISH_OK)))
    result, provider, _, events, _ = run(tmp_path, replies, config=config)

    stuck = [event for event in events.events if event["type"] == "stuck"]
    assert len(stuck) == 2
    assert "same call was made 2 times" in stuck[0]["detail"]
    # The hint reaches the model in the tail of the next step, and only there.
    assert "You seem stuck" in tail(provider, 2)["status"]
    assert "You seem stuck" not in tail(provider, 3)["status"]
    assert result.reason == "stuck"
    assert result.forced
    assert result.finish is not None


def test_different_calls_are_not_stuck(tmp_path):
    config = LoopConfig(repeat_limit=2)
    replies = [reply(call("click", ref=n)) for n in (1, 2, 1, 2)]
    replies.append(reply(call("finish", **FINISH_OK)))
    result, _, _, events, _ = run(tmp_path, replies, config=config)

    assert result.reason == "finished"
    assert "stuck" not in kinds(events)


def test_unchanged_page_counts_as_stuck(tmp_path):
    config = LoopConfig(unchanged_limit=3, repeat_limit=99)
    replies = [reply(call("click", ref=n)) for n in (1, 2, 3)]
    replies.append(reply(call("finish", **FINISH_OK)))
    result, provider, _, events, _ = run(
        tmp_path, replies, executor=FakeExecutor(pages=["same"]), config=config
    )

    stuck = [event for event in events.events if event["type"] == "stuck"]
    assert [event["step"] for event in stuck] == [3]
    assert "has not changed for 3 steps" in stuck[0]["detail"]
    assert "You seem stuck" in tail(provider, 3)["status"]
    assert result.reason == "finished"


def test_failed_calls_return_the_error_and_then_recover(tmp_path):
    config = LoopConfig(failure_limit=2, repeat_limit=99, unchanged_limit=99)
    executor = FakeExecutor([failed("click failed: ref 9 is gone"), failed("click failed: again")])
    replies = [
        reply(call("click", ref=9)),
        reply(call("click", ref=8)),
        reply(call("finish", **FINISH_OK)),
    ]
    result, provider, executor, events, _ = run(tmp_path, replies, executor=executor, config=config)

    first_error = provider.calls[1]["messages"][-2]
    assert isinstance(first_error, ToolMessage)
    assert first_error.is_error
    assert first_error.content == "click failed: ref 9 is gone"
    # After the second failure the agent is taken back to the page it started on.
    assert executor.recovered == ["http://site.test/p1"]
    status = tail(provider, 2)["status"]
    assert "2 steps in a row failed" in status
    assert "Returned to the last page that worked" in status
    assert "recovery" in kinds(events)
    assert result.reason == "finished"


def test_a_success_resets_the_failure_count(tmp_path):
    config = LoopConfig(failure_limit=2, repeat_limit=99, unchanged_limit=99)
    executor = FakeExecutor([failed(), ToolOutcome(True, "ok", acted=True), failed()])
    replies = [reply(call("click", ref=n)) for n in (1, 2, 3)]
    replies.append(reply(call("finish", **FINISH_OK)))
    _, _, executor, _, _ = run(tmp_path, replies, executor=executor, config=config)

    assert executor.recovered == []


def test_reply_without_a_tool_call_is_nudged(tmp_path):
    result, provider, _, events, _ = run(
        tmp_path, [reply(text="Let me think."), reply(call("finish", **FINISH_OK))]
    )

    assert provider.calls[1]["messages"][-2] == AssistantMessage("Let me think.")
    assert tail(provider, 1)["status"] == f"Step 2 of 30.\n{NUDGE}"
    assert "nudge" in kinds(events)
    assert result.reason == "finished"
    assert result.steps == 2


def test_arguments_that_are_not_json_come_back_as_an_error(tmp_path):
    broken = ToolCall("call_x", "click", None, '{"ref": ')
    result, provider, executor, _, _ = run(
        tmp_path, [reply(broken), reply(call("finish", **FINISH_OK))]
    )

    message = provider.calls[1]["messages"][-2]
    assert message.is_error
    assert message.content == BAD_ARGUMENTS
    assert executor.executed == [("finish", FINISH_OK)]
    assert result.reason == "finished"


def test_invalid_finish_is_returned_to_the_model(tmp_path):
    bad = {**FINISH_OK, "retrieved_data": "42 items"}
    result, provider, _, _, _ = run(
        tmp_path, [reply(call("finish", **bad)), reply(call("finish", **FINISH_OK))]
    )

    assert provider.calls[1]["messages"][-2].is_error
    assert result.reason == "finished"
    assert result.steps == 2


def test_only_the_first_tool_call_runs_by_default(tmp_path):
    first, second = call("click", ref=1), call("click", ref=2)
    _, provider, executor, events, _ = run(
        tmp_path, [reply(first, second), reply(call("finish", **FINISH_OK))]
    )

    assert executor.executed[0] == ("click", {"ref": 1})
    assert ("click", {"ref": 2}) not in executor.executed
    skipped = provider.calls[1]["messages"][-2]
    assert skipped == ToolMessage(second.id, EXTRA_CALL, is_error=True)
    logged = [event for event in events.events if event["type"] == "tool_skipped"]
    assert [(event["name"], event["reason"]) for event in logged] == [("click", "single_action")]


def test_the_working_note_is_shown_in_the_tail_until_replaced(tmp_path):
    replies = [
        reply(call("write_note", text="order 12 total: 30.50")),
        reply(call("click", ref=1)),
        reply(call("write_note", text="done: 12, 13")),
        reply(call("finish", **FINISH_OK)),
    ]
    _, provider, _, _, _ = run(tmp_path, replies)

    notes = [tail(provider, index)["notes"] for index in range(4)]
    assert notes == [
        f"Working note:\n{EMPTY_NOTE}",
        "Working note:\norder 12 total: 30.50",
        "Working note:\norder 12 total: 30.50",
        "Working note:\ndone: 12, 13",
    ]
    assert provider.calls[1]["messages"][-2].content == "Note saved."


def test_requested_detail_is_shown_once(tmp_path):
    detail = ToolOutcome(True, "Showed element [9] in full (11 characters).", detail="row A\nrow B")
    replies = [
        reply(call("read_page", section=9, find=None)),
        reply(call("click", ref=1)),
        reply(call("finish", **FINISH_OK)),
    ]
    _, provider, _, _, _ = run(tmp_path, replies, executor=FakeExecutor([detail]))

    shown = [m.content for m in (c["messages"][-1] for c in provider.calls)]
    assert "Detail you asked for:\nrow A\nrow B" in shown[1]
    assert "Detail you asked for" not in shown[0]
    assert "Detail you asked for" not in shown[2]
    # The history keeps the one-line result, not the detail.
    assert all("row A" not in text_of(m) for m in provider.calls[2]["messages"][:-1])


def test_model_error_ends_the_task(tmp_path):
    result, _, _, events, _ = run(tmp_path, [ModelError("request rejected (400)")])

    assert result.reason == "model_error"
    assert "400" in result.error
    assert events.events[-1]["type"] == "task_end"
    failed_call = events.events[-2]
    assert (failed_call["type"], failed_call["attempts"]) == ("model_error", 1)


def test_refusal_ends_the_task(tmp_path):
    result, _, _, _, _ = run(tmp_path, [reply(stop="refusal")])

    assert result.reason == "model_refusal"


def test_prompt_sections_are_totalled_per_task(tmp_path):
    result, _, _, events, _ = run(
        tmp_path, [reply(call("click", ref=1)), reply(call("finish", **FINISH_OK))]
    )

    calls = [event for event in events.events if event["type"] == "model_call"]
    # Each scripted call reports 1000 prompt tokens; the sections share them out.
    assert sum(result.sections.values()) == pytest.approx(2000, abs=8)
    assert result.sections["task"] > 0
    assert result.sections["system"] > result.sections["observation"] > 0
    assert calls[0]["sections"]["history"] == 0
    assert calls[1]["sections"]["history"] > 0


def test_replayed_calls_are_counted_and_cost_nothing(tmp_path):
    from browser_agent.harness.llm import ResponseCache

    cache = ResponseCache(tmp_path / "cache")
    script = [reply(call("click", ref=1)), reply(call("finish", **FINISH_OK))]
    first_client, _, _, _ = make_client(tmp_path, script, cache=cache)
    first = AgentLoop(first_client, FakeExecutor(), EventLog()).run("goal")

    second_client, provider, _, _ = make_client(tmp_path, [], cache=cache)
    second = AgentLoop(second_client, FakeExecutor(), EventLog()).run("goal")

    assert first.replayed_calls == 0
    assert second.replayed_calls == 2
    assert provider.calls == []
    assert second.cost_usd == 0
    assert second.finish == first.finish


# -- several calls in one reply -------------------------------------------------

MULTI = LoopConfig(multi_action=True)


def test_several_calls_run_in_order_when_allowed(tmp_path):
    fill = [
        call("type", ref=1, text="Ann", submit=False),
        call("type", ref=2, text="Lee", submit=False),
    ]
    result, provider, executor, _, _ = run(
        tmp_path,
        [reply(*fill, call("click", ref=3)), reply(call("finish", **FINISH_OK))],
        config=MULTI,
    )

    assert [name for name, _ in executor.executed] == ["type", "type", "click", "finish"]
    results = provider.calls[1]["messages"][2:5]
    assert [m.content for m in results] == ["type done.", "type done.", "click done."]
    # One model call did three actions; the page is read once, after the last.
    assert executor.views == 2
    assert result.steps == 2
    assert provider.calls[0]["system"] == system_prompt(multi_action=True)


def test_calls_after_a_failure_are_not_run(tmp_path):
    executor = FakeExecutor([failed("type failed: element [1] is disabled")])
    calls = [call("type", ref=1, text="Ann", submit=False), call("click", ref=3)]
    _, provider, executor, _, _ = run(
        tmp_path,
        [reply(*calls), reply(call("finish", **FINISH_OK))],
        executor=executor,
        config=MULTI,
    )

    assert [name for name, _ in executor.executed] == ["type", "finish"]
    assert provider.calls[1]["messages"][-2] == ToolMessage(
        calls[1].id, AFTER_FAILURE, is_error=True
    )


def test_calls_after_a_new_page_are_not_run(tmp_path):
    calls = [call("click", ref=1), call("click", ref=2), call("finish", **FINISH_OK)]
    result, provider, executor, _, _ = run(
        tmp_path,
        [reply(*calls), reply(call("finish", **FINISH_OK))],
        executor=FakeExecutor([navigated()]),
        config=MULTI,
    )

    # Neither the second click nor the finish ran: both were written for the old page.
    assert [name for name, _ in executor.executed] == ["click", "finish"]
    skipped = provider.calls[1]["messages"][-3:-1]
    assert [m.content for m in skipped] == [AFTER_NAVIGATION, AFTER_NAVIGATION]
    assert result.steps == 2


def test_a_note_can_ride_along_with_an_action(tmp_path):
    calls = [call("write_note", text="total: 30.50"), call("click", ref=1)]
    _, provider, executor, _, _ = run(
        tmp_path, [reply(*calls), reply(call("finish", **FINISH_OK))], config=MULTI
    )

    assert [name for name, _ in executor.executed] == ["write_note", "click", "finish"]
    assert tail(provider, 1)["notes"] == "Working note:\ntotal: 30.50"
