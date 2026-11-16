"""Event log: append-only on disk, and a replay that rebuilds the step sequence."""

from __future__ import annotations

import json

import pytest

from browser_agent.harness.events import EventLog, read_events, replay
from browser_agent.harness.llm import Usage
from browser_agent.harness.loop import AgentLoop, LoopConfig

from fakes import FINISH_OK, FakeExecutor, call, failed, make_client, navigated, reply


def test_events_are_appended_one_line_each(tmp_path):
    path = tmp_path / "traces" / "events.jsonl"
    log = EventLog(path)

    log.append("task_start", goal="g")
    first = path.read_text(encoding="utf-8")
    log.append("model_call", step=1)

    text = path.read_text(encoding="utf-8")
    assert text.startswith(first)
    assert [json.loads(line)["seq"] for line in text.splitlines()] == [0, 1]
    assert [event["type"] for event in read_events(path)] == ["task_start", "model_call"]


def test_an_existing_log_is_never_overwritten(tmp_path):
    path = tmp_path / "events.jsonl"
    EventLog(path).append("task_start", goal="g")

    with pytest.raises(FileExistsError):
        EventLog(path)

    assert len(read_events(path)) == 1


def test_replay_rebuilds_the_steps_of_a_run(tmp_path):
    usage = Usage(input_tokens=900, cached_input_tokens=100, output_tokens=40)
    client, _, _, _ = make_client(
        tmp_path,
        [
            reply(call("goto", url="http://site.test/orders"), text="Opening orders.", usage=usage),
            reply(call("click", ref=12), usage=usage),
            reply(call("finish", **FINISH_OK), usage=usage),
        ],
    )
    executor = FakeExecutor([navigated("Opened http://site.test/orders."), failed("click failed")])
    path = tmp_path / "events.jsonl"
    result = AgentLoop(client, executor, EventLog(path), LoopConfig()).run("Count the orders")

    rebuilt = replay(read_events(path))

    assert rebuilt.goal == "Count the orders"
    assert len(rebuilt.steps) == result.steps == 3
    assert rebuilt.actions() == [
        ("goto", {"url": "http://site.test/orders"}),
        ("click", {"ref": 12}),
        ("finish", FINISH_OK),
    ]
    assert rebuilt.steps[0].text == "Opening orders."
    assert rebuilt.steps[0].tools[0].ok is True
    assert rebuilt.steps[0].tools[0].content == "Opened http://site.test/orders."
    assert rebuilt.steps[1].tools[0].ok is False
    assert rebuilt.steps[1].tools[0].content == "click failed"
    assert rebuilt.total_tokens == result.usage.total_tokens == 3 * 1040
    assert rebuilt.cost_usd == pytest.approx(result.cost_usd)
    assert rebuilt.finish_reason == "finished"
    assert rebuilt.response == result.finish.response()


def test_replay_keeps_the_page_each_step_was_shown(tmp_path):
    client, _, _, _ = make_client(
        tmp_path, [reply(call("click", ref=1)), reply(call("finish", **FINISH_OK))]
    )
    log = EventLog()
    AgentLoop(client, FakeExecutor(), log, LoopConfig()).run("goal")

    rebuilt = replay(log.events)

    # The history sent to the model has no pages; the log still has every one.
    assert [step.page for step in rebuilt.steps] == ["page p1", "page p2"]
    assert [step.url for step in rebuilt.steps] == ["http://site.test/p1", "http://site.test/p2"]


def test_replay_keeps_forced_steps_and_notes(tmp_path):
    client, _, _, _ = make_client(
        tmp_path,
        [reply(call("click", ref=1)), reply(call("click", ref=1)), reply(text="no answer")],
    )
    config = LoopConfig(repeat_limit=2, max_stuck_hints=0, unchanged_limit=99)
    log = EventLog()
    AgentLoop(client, FakeExecutor(), log, config).run("goal")

    rebuilt = replay(log.events)

    assert [step.forced for step in rebuilt.steps] == [False, False, True]
    assert rebuilt.steps[1].notes == ["stuck: the same call was made 2 times in a row"]
    assert rebuilt.finish_reason == "stuck"
    assert rebuilt.response is None
