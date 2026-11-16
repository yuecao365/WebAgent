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
    BAD_ARGUMENTS,
    EXTRA_CALL,
    NUDGE,
    AgentLoop,
    Budgets,
    LoopConfig,
)

from fakes import FINISH_OK, FakeExecutor, call, failed, make_client, reply, same_page


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


def test_acts_then_finishes(tmp_path):
    result, provider, executor, events, _ = run(
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
    # The task and the first page open the conversation; the tool result follows the call.
    first, second = provider.calls
    assert isinstance(first["messages"][0], UserMessage)
    assert "Task: Find the answer" in first["messages"][0].content
    assert "start page 1" in first["messages"][0].content
    assert [type(m) for m in second["messages"]] == [UserMessage, AssistantMessage, ToolMessage]
    assert "click page 2" in second["messages"][2].content
    assert kinds(events) == [
        "task_start", "model_call", "tool_call", "tool_result",
        "model_call", "tool_call", "tool_result", "task_end",
    ]  # fmt: skip


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


def test_step_budget_forces_a_finish_with_only_the_finish_tool(tmp_path):
    config = LoopConfig(budgets=Budgets(max_steps=2))
    replies = [
        reply(call("click", ref=1)),
        reply(call("click", ref=2)),
        reply(
            call("finish", **{**FINISH_OK, "status": "UNKNOWN_ERROR", "error_details": "ran out"})
        ),
    ]
    result, provider, _, events, _ = run(tmp_path, replies, config=config)

    assert result.reason == "budget_steps"
    assert result.forced
    assert result.finish.status == "UNKNOWN_ERROR"
    assert provider.calls[-1]["tools"] == ["finish"]
    assert "step budget" in provider.calls[-1]["messages"][-1].content
    assert events.events[-1]["reason"] == "budget_steps"
    assert "budget" in kinds(events)


def test_forced_finish_without_an_answer_is_reported(tmp_path):
    config = LoopConfig(budgets=Budgets(max_steps=1))
    result, _, _, _, _ = run(
        tmp_path, [reply(call("click", ref=1)), reply(text="I need more time")], config=config
    )

    assert result.reason == "budget_steps"
    assert result.finish is None
    assert result.error == "no finish call after the budget ran out"


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
    same = lambda: reply(call("click", ref=5))  # noqa: E731
    replies = [same(), same(), same(), same(), reply(call("finish", **FINISH_OK))]
    result, provider, _, events, _ = run(tmp_path, replies, config=config)

    stuck = [event for event in events.events if event["type"] == "stuck"]
    assert len(stuck) == 2
    assert "same call was made 2 times" in stuck[0]["detail"]
    # The hint reaches the model inside the tool result of the repeated call.
    hinted = provider.calls[2]["messages"][-1]
    assert isinstance(hinted, ToolMessage)
    assert "You seem stuck" in hinted.content
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
    executor = FakeExecutor([same_page(), same_page(), same_page(), same_page()])
    replies = [reply(call("click", ref=n)) for n in (1, 2, 3, 4)]
    replies.append(reply(call("finish", **FINISH_OK)))
    result, _, _, events, _ = run(tmp_path, replies, executor=executor, config=config)

    stuck = [event for event in events.events if event["type"] == "stuck"]
    # The first look establishes the page; three more looks at the same page trip it.
    assert [event["step"] for event in stuck] == [4]
    assert "has not changed for 3 steps" in stuck[0]["detail"]
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

    first_error = provider.calls[1]["messages"][-1]
    assert first_error.is_error
    assert first_error.content == "click failed: ref 9 is gone"
    # After the second failure the agent is taken back to the page it started on.
    assert executor.recovered == ["http://site.test/p1"]
    second_error = provider.calls[2]["messages"][-1]
    assert "2 tool calls in a row failed" in second_error.content
    assert "Returned to the last page that worked" in second_error.content
    assert "recovery" in kinds(events)
    assert result.reason == "finished"


def test_a_success_resets_the_failure_count(tmp_path):
    config = LoopConfig(failure_limit=2, repeat_limit=99, unchanged_limit=99)
    executor = FakeExecutor([failed(), same_page("a"), failed()])
    replies = [reply(call("click", ref=n)) for n in (1, 2, 3)]
    replies.append(reply(call("finish", **FINISH_OK)))
    _, _, executor, _, _ = run(tmp_path, replies, executor=executor, config=config)

    assert executor.recovered == []


def test_reply_without_a_tool_call_is_nudged(tmp_path):
    result, provider, _, events, _ = run(
        tmp_path, [reply(text="Let me think."), reply(call("finish", **FINISH_OK))]
    )

    assert provider.calls[1]["messages"][-1] == UserMessage(NUDGE)
    assert "nudge" in kinds(events)
    assert result.reason == "finished"
    assert result.steps == 2


def test_arguments_that_are_not_json_come_back_as_an_error(tmp_path):
    broken = ToolCall("call_x", "click", None, '{"ref": ')
    result, provider, executor, _, _ = run(
        tmp_path, [reply(broken), reply(call("finish", **FINISH_OK))]
    )

    message = provider.calls[1]["messages"][-1]
    assert message.is_error
    assert message.content == BAD_ARGUMENTS
    assert executor.executed == [("finish", FINISH_OK)]
    assert result.reason == "finished"


def test_invalid_finish_is_returned_to_the_model(tmp_path):
    bad = {**FINISH_OK, "retrieved_data": "42 items"}
    result, provider, _, _, _ = run(
        tmp_path, [reply(call("finish", **bad)), reply(call("finish", **FINISH_OK))]
    )

    assert provider.calls[1]["messages"][-1].is_error
    assert result.reason == "finished"
    assert result.steps == 2


def test_only_the_first_tool_call_of_a_reply_runs(tmp_path):
    first, second = call("click", ref=1), call("click", ref=2)
    _, provider, executor, _, _ = run(
        tmp_path, [reply(first, second), reply(call("finish", **FINISH_OK))]
    )

    assert executor.executed[0] == ("click", {"ref": 1})
    assert ("click", {"ref": 2}) not in executor.executed
    skipped = provider.calls[1]["messages"][-1]
    assert skipped == ToolMessage(second.id, EXTRA_CALL, is_error=True)


def test_model_error_ends_the_task(tmp_path):
    result, _, _, events, _ = run(tmp_path, [ModelError("request rejected (400)")])

    assert result.reason == "model_error"
    assert "400" in result.error
    assert events.events[-1]["type"] == "task_end"


def test_refusal_ends_the_task(tmp_path):
    result, _, _, _, _ = run(tmp_path, [reply(stop="refusal")])

    assert result.reason == "model_refusal"


def test_history_view_decides_what_the_model_sees(tmp_path):
    """The plug point later context components use: here, keep only the last message."""
    client, provider, _, _ = make_client(
        tmp_path, [reply(call("click", ref=1)), reply(call("finish", **FINISH_OK))]
    )
    loop = AgentLoop(client, FakeExecutor(), EventLog(), view_messages=lambda m: m[-1:])
    loop.run("goal")

    assert [len(c["messages"]) for c in provider.calls] == [1, 1]
