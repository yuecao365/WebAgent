"""With every switch at its default, the model is sent what the baseline code sent.

baseline_test_r1 and r2 were run by commit fa8aef6. They stay valid samples of the
baseline only while the requests the harness sends, in a clean environment and with
no memory component on, are the bytes that commit sent. The fixture holds those
bytes for one fixed fake episode (see request_episode.py for how it was recorded);
the tests run the same episode through the code as it is now.

A change that is meant to alter the default request has to re-record the fixture, and
with that says that later runs are no longer comparable with r1 and r2.
"""

from __future__ import annotations

import json

from browser_agent.eval.runner import RunConfig
from browser_agent.harness.events import read_events
from request_episode import (
    ORDERS_LINK,
    SITE,
    TASK_ID,
    as_lines,
    episode_browser,
    run_episode,
)

from fakes import FIXTURES

FIXTURE = FIXTURES / "requests_fa8aef6.jsonl"
NEW_TAB = f"{SITE}/admin/catalog/product/edit/id/1604/"


def recorded() -> list[str]:
    # Lines, not the file's bytes: a checkout may change the line endings between
    # the bodies, never the bodies themselves (they are ASCII without line breaks).
    return FIXTURE.read_text(encoding="ascii").splitlines()


def events_of(run_dir):
    return read_events(run_dir / "traces" / str(TASK_ID) / "events.jsonl")


def test_default_requests_are_byte_identical_to_those_of_the_baseline_code(tmp_path):
    requests, _ = run_episode(tmp_path)

    assert as_lines(requests) == recorded()


def test_the_recorded_episode_covers_what_a_run_does():
    bodies = [json.loads(line) for line in recorded()]
    last = bodies[-1]
    outputs = [
        item["output"] for item in last["input"] if item.get("type") == "function_call_output"
    ]
    called = [item["name"] for item in last["input"] if item.get("type") == "function_call"]
    pages = [body["input"][-1]["content"] for body in bodies]

    assert len(bodies) == 10
    # The defaults of the baseline: Responses API, low effort, one call per step.
    assert last["reasoning"] == {"effort": "low"}
    assert last["parallel_tool_calls"] is False
    assert last["prompt_cache_key"] == "browser-agent-2026-01-01_fixture-7"
    assert [tool["name"] for tool in last["tools"]] == [
        "click", "type", "goto", "scroll", "read_page", "write_note", "finish",
    ]  # fmt: skip
    # Every tool but finish is in the history, with a failed call and a reply without one.
    assert set(called) == {"click", "type", "read_page", "write_note", "scroll", "goto"}
    assert any(output.startswith("click failed:") for output in outputs)
    assert any(item.get("role") == "assistant" for item in last["input"])
    assert any(item.get("type") == "reasoning" for item in last["input"])
    # The default view cut the long table, and a search reached into the cut part.
    assert any("more rows not shown" in page for page in pages)
    assert any("Detail you asked for:" in page for page in pages)
    assert any("Working note:\nOrder 150" in page for page in pages)


def test_a_switch_that_is_turned_on_or_off_does_change_the_bytes(tmp_path):
    """The comparison is not blind: the fixture is of the defaults and nothing else."""
    config = RunConfig.model_validate({"name": "fixture", "switches": {"truncate_lists": False}})

    requests, _ = run_episode(tmp_path, config=config)

    assert as_lines(requests) != recorded()
    assert as_lines(requests)[0] == recorded()[0]  # the first page has no long list


def test_a_repaired_environment_sends_the_same_bytes(tmp_path):
    """The check before a task works beside the model's requests, never in them."""
    browser = episode_browser()
    browser.other_tabs = [NEW_TAB]
    browser.visible = False

    requests, run_dir = run_episode(tmp_path, browser=browser)

    assert as_lines(requests) == recorded()
    repaired = [event for event in events_of(run_dir) if event["type"] == "env_repaired"]
    assert repaired[0]["problems"] == [f"1 extra tab(s) open: {NEW_TAB}"]


def test_a_new_tab_changes_the_result_of_the_action_that_opened_it_and_nothing_else(tmp_path):
    browser = episode_browser()
    # The first click loads the orders page and also opens a tab.
    browser.new_tab_links[ORDERS_LINK] = NEW_TAB
    note = f"A new tab opened at {NEW_TAB}; it was closed. Use goto with that URL to open it here."
    expected = [json.loads(line) for line in recorded()]
    for body in expected:
        for item in body["input"]:
            if item.get("type") == "function_call_output" and item["call_id"] == "call_001":
                item["output"] = item["output"].replace("Clicked [104].", f"Clicked [104]. {note}")

    requests, run_dir = run_episode(tmp_path, browser=browser)

    assert as_lines(requests) == as_lines(expected)
    # The request before the click is untouched; every later one carries the one line.
    assert as_lines(requests)[0] == recorded()[0]
    assert all(
        now != then for now, then in zip(as_lines(requests)[1:], recorded()[1:], strict=True)
    )
    assert [e["url"] for e in events_of(run_dir) if e["type"] == "new_tab"] == [NEW_TAB]
