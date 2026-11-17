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

import itertools
import json
from types import SimpleNamespace

from browser_agent.eval.runner import RunConfig
from browser_agent.harness.events import read_events
from browser_agent.memory.skill import Skill, parse_skill_md
from browser_agent.memory.store import MemoryStore
from request_episode import (
    ORDERS_LINK,
    SITE,
    TASK_ID,
    as_lines,
    episode_browser,
    episode_replies,
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


# -- with memory switched on ----------------------------------------------------

OPEN_ORDERS = """---
name: open-order-grid
description: Open the order grid.
version: 1
params: {}
url_pattern: "^/"
---

1. Open /sales/order/. Check: the search box of the grid is there.
"""
OPEN_ORDERS_CODE = (
    'def run():\n    goto("/sales/order/")\n    check(role="textbox", name="Search by keyword")\n'
)
MEMORY_ON = {
    "name": "fixture",
    "memory_build": "b",
    "switches": {"skills": True, "site_facts": True, "lessons": True},
}
LESSON = "On the order grid, search by the order number before reading the rows."


def memory_build(root):
    meta, body = parse_skill_md(OPEN_ORDERS)
    store = MemoryStore.create(root / "memory_store" / "b", {"name": "b"})
    store.add_skill(Skill(meta, body, OPEN_ORDERS_CODE), {"task_id": 1})
    store.add("site_fact", "fact-001", "Orders are under SALES > Orders.", "^/sales/", [{}])
    store.add("lesson", "lesson-001", LESSON, "^/sales/order/?$", [{}])
    store.write_manifest()
    store.close()


def test_with_memory_on_the_prefix_is_fixed_and_lessons_follow_the_page(tmp_path):
    memory_build(tmp_path)
    plain = [json.loads(line) for line in recorded()]

    requests, run_dir = run_episode(tmp_path, config=RunConfig.model_validate(MEMORY_ON))

    assert len(requests) == len(plain)
    prefix = requests[0]["input"][0]
    assert prefix["content"].startswith("Notes from earlier work on this site.")
    assert "- open-order-grid: Open the order grid. (starts on ^/; has code)" in prefix["content"]
    assert "- Orders are under SALES > Orders. (pages ^/sales/)" in prefix["content"]
    for request, before in zip(requests, plain, strict=True):
        # The same message in front of every request; the task comes right after it.
        assert request["input"][0] == prefix
        assert request["input"][1] == before["input"][0]
        assert [tool["name"] for tool in request["tools"]][-2:] == ["load_skill", "run_skill"]
        assert request["instructions"] == before["instructions"]
        # A lesson is in the tail exactly while the page is the order grid.
        tail = request["input"][-1]["content"]
        on_grid = "URL: http://site.test/admin/sales/order/\n" in tail
        assert (LESSON in tail) is on_grid
    # Everything but the tail only grows at its end, so the cache keeps working.
    for earlier, later in itertools.pairwise(requests):
        stable = earlier["input"][:-1]
        assert later["input"][: len(stable)] == stable
    record = json.loads((run_dir / "records.jsonl").read_text(encoding="utf-8"))
    assert record["memory_used"] == {
        "skills_loaded": [], "skills_run": [], "skills_guided": [],
        "lessons_shown": ["lesson-001@v1"],
    }  # fmt: skip
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    assert config["memory"] == {
        "skills": ["open-order-grid@v1"],
        "site_facts": ["fact-001@v1"],
        "lessons": ["lesson-001@v1"],
    }


def test_a_skill_run_by_the_model_goes_through_the_gate_and_leaves_its_events(tmp_path):
    memory_build(tmp_path)
    replies = episode_replies()
    run_skill = {"name": "open-order-grid", "args": "{}"}
    replies[0].output[-1] = SimpleNamespace(
        type="function_call", call_id="call_001", name="run_skill", arguments=json.dumps(run_skill)
    )

    requests, run_dir = run_episode(
        tmp_path, replies=replies, config=RunConfig.model_validate(MEMORY_ON)
    )

    result = next(
        item["output"]
        for item in requests[1]["input"]
        if item.get("type") == "function_call_output" and item["call_id"] == "call_001"
    )
    assert result == (
        "Skill open-order-grid ran: 2 steps, every check held. The task is not finished yet: "
        "look at the page now shown, then finish."
    )
    # The code took the agent to the grid: the next page shown is the grid.
    assert "URL: http://site.test/admin/sales/order/\n" in requests[1]["input"][-1]["content"]
    kinds = [event["type"] for event in events_of(run_dir)]
    assert kinds.index("gate_passed") < kinds.index("skill_code_run") < kinds.index("tool_result")
    record = json.loads((run_dir / "records.jsonl").read_text(encoding="utf-8"))
    assert record["memory_used"]["skills_run"] == ["open-order-grid@v1"]
    assert record["finish_reason"] == "finished"
