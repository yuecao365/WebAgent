"""Memory in a run: the two skill tools, the gate, the guided fallback, the prefix
and the lessons. Offline, on pages saved from the local site."""

from __future__ import annotations

import json

import pytest

from browser_agent.eval.fallbacks import task_fallbacks
from browser_agent.harness.events import EventLog
from browser_agent.harness.loop import LESSONS_HEAD, AgentLoop, LoopConfig
from browser_agent.harness.tools import TOOLS, ToolExecutor
from browser_agent.memory.library import (
    MAX_LESSONS_SHOWN,
    Memory,
    capped_facts,
    load_memory,
)
from browser_agent.memory.runtime import SKILL_TOOLS, SkillTools
from browser_agent.memory.skill import Skill, parse_skill_md
from browser_agent.memory.store import Item, MemoryStore, StoreError

from fakes import (
    FINISH_OK,
    SHOP_BASE,
    SHOP_ORDER,
    FakeExecutor,
    call,
    make_client,
    navigated,
    reply,
    shop_browser,
)

SKILL_MD = """---
name: read-order-total
description: Read the grand total of an order.
version: 2
params:
  order_number: {type: string, description: As the grid shows it}
url_pattern: "^/sales/order/?$"
required_elements:
  - {role: link, name: View, row: "{order_number}"}
preconditions:
  - {role: button, name: Filters}
---

1. Click "View" in the row of the order. Check: the heading shows the order number.
2. Read the row "Grand Total".
"""
CODE = """def run(order_number):
    click(role="link", name="View", row=order_number)
    check(text="Order # " + order_number)
    total = read(role="row", name="", row="Grand Total")
    return_value(total.replace("Grand Total", "").strip())
"""
ARGS = json.dumps({"order_number": "000000299"})


def skill(md=SKILL_MD, code=CODE):
    meta, body = parse_skill_md(md)
    return Skill(meta, body, code)


def tools(*skills, browser=None):
    browser = browser or shop_browser()
    events = []
    library = {item.name: item for item in (skills or (skill(),))}
    skill_tools = SkillTools(
        library,
        browser,
        SHOP_BASE,
        ["http://site.test"],
        notify=lambda kind, **details: events.append((kind, details)),
    )
    return skill_tools, browser, events


def kinds(events):
    return [kind for kind, _ in events]


# -- load_skill -----------------------------------------------------------------


def test_load_skill_shows_the_parameters_and_the_steps_without_acting():
    skill_tools, browser, events = tools()

    outcome = skill_tools.load("read-order-total")

    assert outcome.ok
    assert not outcome.acted
    assert outcome.summary.startswith(
        "Skill read-order-total. It has verified code: run_skill can carry it out.\n"
        "Parameters: order_number (string): As the grid shows it.\n\n"
        '1. Click "View" in the row of the order.'
    )
    assert events == [("skill_loaded", {"skill": "read-order-total", "version": 2})]
    assert browser.clicks == []


def test_load_skill_says_when_a_skill_is_steps_only():
    skill_tools, _, _ = tools(skill(code=None))

    assert "It has no verified code: follow the steps yourself." in (
        skill_tools.load("read-order-total").summary
    )


# -- run_skill: the gate passes ------------------------------------------------


def test_run_skill_runs_the_code_when_the_gate_passes():
    skill_tools, browser, events = tools()

    outcome = skill_tools.run("read-order-total", ARGS)

    assert outcome.ok
    assert outcome.navigated
    assert outcome.summary == (
        'Skill read-order-total ran: 4 steps, every check held. It returned: "$219.40". '
        "The task is not finished yet: look at the page now shown, then finish."
    )
    assert browser.url == SHOP_ORDER
    assert kinds(events) == ["gate_passed", "skill_code_run"]
    run = events[1][1]
    assert (run["ok"], run["steps"], run["returned"]) == (True, 4, True)
    assert run["args"] == {"order_number": "000000299"}
    # A skill never finishes the task.
    assert outcome.finish is None


# -- run_skill: the gate rejects, each check on its own ------------------------


def rejected(skill_tools, browser, events, check, why, args=ARGS):
    outcome = skill_tools.run("read-order-total", args)

    # Not an error: following the steps is the default path.
    assert outcome.ok
    assert outcome.summary.startswith(f"Skill read-order-total was not run: {why}")
    assert "Nothing was executed. Follow its steps yourself" in outcome.summary
    assert '1. Click "View" in the row of the order.' in outcome.summary
    assert browser.clicks == []
    assert kinds(events) == ["gate_rejected", "skill_guided"]
    assert events[0][1]["check"] == check
    assert events[1][1]["reason"] == check


def test_the_gate_rejects_a_skill_without_code():
    rejected(*tools(skill(code=None)), "no_code", "this skill has no verified code")


def test_the_gate_rejects_on_a_page_whose_address_does_not_match():
    browser = shop_browser()
    browser.url = SHOP_ORDER

    rejected(*tools(browser=browser), "url_pattern", "the page's address /sales/order/view/")


def test_the_gate_rejects_when_a_required_element_is_missing():
    rejected(
        *tools(),
        "required_element",
        '0 elements match link "View" in the row showing "000009999"',
        args=json.dumps({"order_number": "000009999"}),
    )


def test_the_gate_rejects_when_a_precondition_does_not_hold():
    changed = skill(SKILL_MD.replace("name: Filters", "name: Unfilter"))

    rejected(*tools(changed), "precondition", '0 elements match button "Unfilter"')


# -- run_skill: a step fails ---------------------------------------------------


def test_a_failed_step_stops_the_code_and_hands_the_steps_to_the_model():
    wrong = skill(code=CODE.replace('"Order # " + order_number', '"Order # 000000300"'))
    skill_tools, _browser, events = tools(wrong)

    outcome = skill_tools.run("read-order-total", ARGS)

    assert outcome.ok
    assert outcome.navigated  # the click before the failed check did change the page
    assert outcome.summary.startswith(
        "Skill read-order-total stopped at step 2, check(text='Order # 000000300'): "
        'check failed: the page does not show "Order # 000000300"\n'
        "These calls had been carried out before it:\n"
        "  1. click(role='link', name='View', row='000000299')\n"
        "Nothing after that was done. Look at the page now shown and continue yourself"
    )
    assert "2. Read the row" in outcome.summary
    assert kinds(events) == ["gate_passed", "skill_code_run", "skill_step_failed", "skill_guided"]
    assert events[1][1]["ok"] is False
    assert (events[2][1]["step"], events[2][1]["call"]) == (2, "check")
    assert events[3][1]["reason"] == "step_failed"


# -- run_skill: what is not a skill run at all ---------------------------------


@pytest.mark.parametrize(
    ("args", "why"),
    [
        ("not json", "Invalid arguments for skill read-order-total"),
        ("[1, 2]", "not an object"),
        ("{}", "missing argument 'order_number' (string)"),
        ('{"order_number": 299}', "must be a string"),
        ('{"order_number": "1", "extra": 2}', "unknown argument 'extra'"),
    ],
)
def test_arguments_that_do_not_fit_are_an_error_before_the_gate(args, why):
    skill_tools, _browser, events = tools()

    outcome = skill_tools.run("read-order-total", args)

    assert not outcome.ok
    assert why in outcome.summary
    assert "Parameters: order_number (string)" in outcome.summary
    assert events == []


def test_an_unknown_skill_is_an_error_that_lists_the_skills():
    skill_tools, _, events = tools()

    for outcome in (skill_tools.load("cancel-order"), skill_tools.run("cancel-order", "{}")):
        assert not outcome.ok
        assert outcome.summary == "No skill named 'cancel-order'. Skills: read-order-total."
    assert events == []


# -- through the tool executor -------------------------------------------------


def test_the_skill_tools_exist_only_when_they_are_added():
    plain = ToolExecutor(shop_browser(), allowed_origins=["http://site.test"])
    skill_tools, browser, _ = tools()
    with_skills = ToolExecutor(browser, allowed_origins=["http://site.test"], extra=skill_tools)

    assert plain.tools == TOOLS
    assert with_skills.tools == (*TOOLS, *SKILL_TOOLS)
    assert [spec.name for spec in SKILL_TOOLS] == ["load_skill", "run_skill"]
    assert (
        "Unknown tool 'run_skill'"
        in plain.execute("run_skill", {"name": "x", "args": "{}"}).summary
    )
    ran = with_skills.execute("run_skill", {"name": "read-order-total", "args": ARGS})
    assert ran.summary.startswith("Skill read-order-total ran: 4 steps")
    missing = with_skills.execute("run_skill", {"name": "read-order-total"})
    assert missing.summary.startswith("Invalid arguments for run_skill: args")


@pytest.mark.parametrize("spec", SKILL_TOOLS, ids=lambda spec: spec.name)
def test_the_skill_tool_schemas_are_strict(spec):
    schema = spec.parameters

    assert schema["additionalProperties"] is False
    assert schema["required"] == list(schema["properties"])
    assert set(schema["properties"]) == set(spec.args_model.model_fields)


# -- the prefix, the facts and the lessons -------------------------------------


def item(kind, item_id, text, pattern="^/", sources=1, version=1):
    return Item(kind, item_id, version, "active", "2026-01-01", pattern, text, [{}] * sources)


def test_memory_with_nothing_switched_on_has_no_prefix():
    assert Memory(build="b").prefix() is None


def test_the_prefix_lists_skills_by_name_description_and_address_then_the_facts():
    memory = Memory(
        build="b",
        skills={
            "read-order-total": skill(),
            "guide": skill(SKILL_MD.replace("read-order-total", "guide"), None),
        },
        site_facts=(item("site_fact", "fact-001", "Orders are under SALES > Orders.", "^/sales/"),),
    )

    prefix = memory.prefix()

    assert prefix.startswith("Notes from earlier work on this site.")
    assert (
        "- read-order-total: Read the grand total of an order. "
        "(starts on ^/sales/order/?$; has code)" in prefix
    )
    assert (
        "- guide: Read the grand total of an order. (starts on ^/sales/order/?$; steps only)"
        in prefix
    )
    assert "Site facts:\n- Orders are under SALES > Orders. (pages ^/sales/)" in prefix
    assert prefix.index("Skills:") < prefix.index("Site facts:")
    assert memory.versions() == {
        "skills": ["read-order-total@v2", "guide@v2"],
        "site_facts": ["fact-001@v1"],
        "lessons": [],
    }


def test_site_facts_are_capped_keeping_those_seen_in_most_episodes():
    facts = [
        item("site_fact", "fact-001", "a" * 100, sources=1),
        item("site_fact", "fact-002", "b" * 100, sources=3),
        item("site_fact", "fact-003", "c" * 100, sources=2),
    ]

    kept = capped_facts(facts, max_chars=240)

    # Room for two: the ones from three and from two episodes, listed in id order.
    assert [fact.id for fact in kept] == ["fact-002", "fact-003"]
    assert [fact.id for fact in capped_facts(facts)] == ["fact-001", "fact-002", "fact-003"]


def test_lessons_are_those_whose_pattern_matches_the_page():
    lessons = tuple(
        item("lesson", f"lesson-{n:03d}", f"Lesson {n}.", pattern)
        for n, pattern in enumerate(
            ["^/sales/order/?$", "^/review/", "^/sales/", "^/sales/order/", "^/sales/order/?$"], 1
        )
    )
    memory = Memory(build="b", lessons=lessons)

    assert [lesson.id for lesson in memory.lessons_at("/review/product/")] == ["lesson-002"]
    assert memory.lessons_at("/catalog/product/") == []
    on_grid = memory.lessons_at("/sales/order/")
    assert len(on_grid) == MAX_LESSONS_SHOWN
    assert [lesson.id for lesson in on_grid] == ["lesson-001", "lesson-003", "lesson-004"]


def build(tmp_path):
    store = MemoryStore.create(tmp_path / "memory_store" / "b", {"name": "b"})
    store.add_skill(skill(SKILL_MD.replace("version: 2", "version: 1"), None), {"task_id": 1})
    store.add_skill(skill(), {"task_id": 1}, note="code verified")
    store.add("site_fact", "fact-001", "Orders are under SALES > Orders.", "^/sales/", [{}])
    store.add("lesson", "lesson-001", "Filter the grid by status first.", "^/sales/order/?$", [{}])
    store.add("lesson", "lesson-002", "Old wording.", "^/x/", [{}])
    store.retire("lesson", "lesson-002", "wrong")
    store.write_manifest()
    store.close()
    return tmp_path


def test_a_run_takes_from_a_build_only_what_its_switches_allow(tmp_path):
    root = build(tmp_path)

    everything = load_memory(root, "b", skills=True, site_facts=True, lessons=True)
    facts_only = load_memory(root, "b", skills=False, site_facts=True, lessons=False)

    # The active version of the skill (the verified one), no retired lesson.
    assert everything.skills["read-order-total"].code == CODE
    assert [lesson.label for lesson in everything.lessons] == ["lesson-001@v1"]
    assert (facts_only.skills, facts_only.lessons) == ({}, ())
    assert [fact.label for fact in facts_only.site_facts] == ["fact-001@v1"]
    with pytest.raises(StoreError, match="is not a memory build"):
        load_memory(root, "missing", skills=True, site_facts=False, lessons=False)


# -- the loop ------------------------------------------------------------------

PREFIX = "Notes from earlier work on this site.\n\nSkills: ...\n- read-order-total: ..."


def lessons_at(url):
    return [("lesson-001@v1", "Filter the grid by status first.")] if url.endswith("/p2") else []


def run_loop(tmp_path, replies, **settings):
    llm, provider, _, _ = make_client(tmp_path, replies)
    log = EventLog()
    executor = FakeExecutor([navigated(), navigated()])
    AgentLoop(llm, executor, log, LoopConfig(**settings)).run("Find it")
    return provider, log.events


def shown(message):
    """What a message says, whether it is the model's or not."""
    if hasattr(message, "content"):
        return message.content
    return (message.text, [(c.name, c.raw_arguments) for c in message.tool_calls])


STEPS = [
    reply(call("click", ref=1)),
    reply(call("click", ref=2)),
    reply(call("finish", **FINISH_OK)),
]


def test_the_memory_prefix_is_one_fixed_message_in_front_of_the_task(tmp_path):
    provider, _ = run_loop(
        tmp_path, STEPS, memory_prefix=PREFIX, tools=(*TOOLS, *SKILL_TOOLS), lessons_at=lessons_at
    )

    for request in provider.calls:
        first, task = request["messages"][0], request["messages"][1]
        assert first.content == PREFIX
        assert task.content == "Task: Find it"
        assert request["tools"][-2:] == ["load_skill", "run_skill"]
    # The cached part only grows at its end: every request starts with the one before
    # it, minus that one's tail.
    for before, after in zip(provider.calls, provider.calls[1:], strict=False):
        stable = before["messages"][:-1]
        assert [shown(m) for m in after["messages"][: len(stable)]] == [shown(m) for m in stable]


def test_lessons_appear_in_the_tail_only_on_pages_they_match(tmp_path):
    provider, events = run_loop(tmp_path, STEPS, lessons_at=lessons_at)

    tails = [request["messages"][-1].content for request in provider.calls]

    # Pages p1, p2, p3: the lesson matches p2 only.
    assert [LESSONS_HEAD in tail for tail in tails] == [False, True, False]
    assert f"{LESSONS_HEAD}\n- Filter the grid by status first." in tails[1]
    # In the tail, after the page and before the note; never in the stable part.
    assert tails[1].index("Current page:") < tails[1].index(LESSONS_HEAD)
    assert tails[1].index(LESSONS_HEAD) < tails[1].index("Working note:")
    assert all(LESSONS_HEAD not in str(shown(m)) for m in provider.calls[2]["messages"][:-1])
    logged = [event for event in events if event["type"] == "lesson_shown"]
    assert [(event["lesson"], event["step"]) for event in logged] == [("lesson-001@v1", 2)]


def test_without_memory_the_messages_and_tools_are_as_before(tmp_path):
    provider, events = run_loop(tmp_path, STEPS)

    assert provider.calls[0]["messages"][0].content == "Task: Find it"
    assert provider.calls[0]["tools"] == [tool.name for tool in TOOLS]
    assert not any(event["type"] == "lesson_shown" for event in events)


# -- the ledger ----------------------------------------------------------------


def test_memory_events_are_counted_in_the_fallback_ledger(tmp_path):
    _, events = run_loop(tmp_path, STEPS, lessons_at=lessons_at)
    log = EventLog()
    log.events = list(events[:5])
    details = {"skill": "read-order-total", "version": 2}
    log.append("skill_loaded", **details)
    log.append("gate_rejected", check="url_pattern", detail="...", **details)
    log.append("skill_guided", reason="url_pattern", **details)
    log.append("gate_passed", **details)
    log.append("skill_code_run", ok=False, steps=2, seconds=1.0, returned=False, **details)
    log.append("skill_step_failed", step=2, call="check", error="...", **details)
    log.append("skill_guided", reason="step_failed", **details)
    log.events += events[5:]

    fired = [(item.key, item.recovered) for item in task_fallbacks(log.events)]

    assert fired == [
        ("skill_loaded", None),
        ("gate_rejected", None),
        ("skill_guided", True),
        ("gate_passed", False),  # the code did not run through
        ("skill_step_failed", None),
        ("skill_guided", True),
        ("lesson_shown", None),
    ]
