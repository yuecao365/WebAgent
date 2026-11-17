"""Building memory from learn episodes, with a scripted model and synthetic traces."""

from __future__ import annotations

import json

import pytest

from browser_agent.harness.events import EventLog
from browser_agent.harness.llm import ToolCall
from browser_agent.memory.build import (
    BuildError,
    Note,
    check_candidate,
    extract_facts,
    induce_skill,
    merge_notes,
    reflect,
    task_literals,
)
from browser_agent.memory.episodes import (
    element_on_page,
    failures,
    load_episodes,
    match_slots,
    names_an_instance,
    shortest_successes,
    without_site,
)
from browser_agent.memory.pipeline import BuildConfig, induce, learn_entries, read_log
from browser_agent.memory.store import MemoryStore, StoreError

from fakes import make_client, reply


def call(name, **arguments):
    """A tool call whose arguments may themselves have a field called name."""
    return tool_call(name, arguments)


def tool_call(name, arguments):
    return ToolCall(f"call_{name}", name, arguments, json.dumps(arguments))


GRID = """URL: http://localhost:7780/admin/sales/order/
Title: Orders

[10] link " SALES"
table
 [20] row: [21] checkbox | 000000302 | Jane Doe | Pending | [22] link "View"
 [30] row: [31] checkbox | 000000299 | Sarah Miller | Pending | [32] link "View"
"""
ORDER = """URL: http://localhost:7780/admin/sales/order/view/order_id/302/
Title: #000000302

[40] button "Cancel"
Order # 000000302
"""
DONE = ORDER.replace('[40] button "Cancel"', "You canceled the order.")
ENTRIES = [
    {"task_id": 470, "template_id": 257, "split": "learn", "task_type": "mutate",
     "state_changing": True, "intent": "Cancel order 302",
     "intent_template": "Cancel order {{id}}"},
    {"task_id": 471, "template_id": 257, "split": "test", "task_type": "mutate",
     "state_changing": True, "intent": "Cancel order 299"},
    {"task_id": 107, "template_id": 270, "split": "learn", "task_type": "retrieve",
     "state_changing": False, "intent": 'Count orders of "Jane Doe" in 2022'},
]  # fmt: skip


def write_run(root, name, tasks):
    """A run directory with records and event logs, as the runner leaves them."""
    run_dir = root / "results" / name
    run_dir.mkdir(parents=True)
    records = []
    for task_id, template_id, success, steps in tasks:
        log = EventLog(run_dir / "traces" / str(task_id) / "events.jsonl")
        log.append("task_start", goal="g", log_version=3)
        for page, tool, arguments, result in steps:
            url = page.splitlines()[0].removeprefix("URL: ")
            log.append("observation", step=1, url=url, title="T", text=page)
            log.append("tool_call", step=1, name=tool, arguments=arguments)
            log.append("tool_result", step=1, name=tool, ok=True, content=result)
        log.append(
            "observation", step=9, url="http://localhost:7780/admin/x/", title="T", text=DONE
        )
        log.append("tool_call", step=9, name="finish", arguments={"status": "SUCCESS"})
        log.append("tool_result", step=9, name="finish", ok=True, content="Task finished.")
        log.append("task_end", reason="finished", response={"status": "SUCCESS"})
        records.append(
            {"task_id": task_id, "template_id": template_id, "success": success,
             "steps": len(steps) + 1, "finish_reason": "finished"}
        )  # fmt: skip
    (run_dir / "records.jsonl").write_text(
        "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
    )


CANCEL_STEPS = [
    (GRID, "click", {"ref": 22}, 'Clicked [22] "View". Now on: T (http://localhost:7780/admin/sales/order/view/order_id/302/)'),
    (ORDER, "click", {"ref": 40}, 'Clicked [40] "Cancel".'),
]  # fmt: skip
DETOUR = [(GRID, "click", {"ref": 10}, 'Clicked [10] "SALES".'), *CANCEL_STEPS]


@pytest.fixture
def learn_runs(tmp_path):
    write_run(tmp_path, "run_a", [(470, 257, True, DETOUR), (107, 270, False, CANCEL_STEPS)])
    write_run(tmp_path, "run_b", [(470, 257, True, CANCEL_STEPS), (471, 257, True, CANCEL_STEPS)])
    (tmp_path / "configs").mkdir()
    templates = [
        {"template_id": 257, "intent_template": "Cancel order {{id}}"},
        {"template_id": 270, "intent_template": 'Count orders of "{{customer}}" in {{year}}'},
    ]
    (tmp_path / "configs" / "subset.json").write_text(
        json.dumps({"tasks": ENTRIES, "templates": templates}), encoding="utf-8"
    )
    return tmp_path


def episodes(root):
    learn = [entry for entry in ENTRIES if entry["split"] == "learn"]
    return load_episodes(root / "results", ["run_a", "run_b"], learn)


# -- episodes ---------------------------------------------------------------


def test_episodes_are_read_from_traces_with_the_elements_by_role_and_name(learn_runs):
    found = episodes(learn_runs)
    episode = next(e for e in found if e.key == "run_b/470")

    # Only learn tasks: task 471 of run_b is a test task and is never loaded.
    assert sorted(e.key for e in found) == ["run_a/107", "run_a/470", "run_b/470"]
    assert [(step.call, step.element) for step in episode.steps] == [
        (
            "click",
            'link "View", in the table row: checkbox | 000000302 | Jane Doe | Pending | '
            'link "View"',
        ),
        ("click", 'button "Cancel"'),
    ]  # fmt: skip
    assert episode.steps[0].path == "/sales/order/"
    assert episode.answer == {"status": "SUCCESS"}
    assert "You canceled the order." in episode.final_page


def test_an_episode_is_rendered_without_refs_or_the_sites_address(learn_runs):
    text = next(e for e in episodes(learn_runs) if e.key == "run_b/470").render()

    assert text.startswith("Task: Cancel order 302\n")
    assert "Step 1. On page /sales/order/" in text
    assert 'Result: Clicked "View". Now on: T (/sales/order/view/order_id/302/)' in text
    assert "localhost" not in text
    assert "[22]" not in text
    assert "At the end the agent was on page /x/" in text
    assert 'The agent\'s final answer: {"status": "SUCCESS"}' in text


def test_the_source_of_a_skill_is_the_shortest_successful_episode(learn_runs):
    found = episodes(learn_runs)

    sources = shortest_successes(found)

    # Template 270 never succeeded and gets no skill; its episode is one to learn from.
    assert {template: e.key for template, e in sources.items()} == {257: "run_b/470"}
    assert [e.key for e in failures(found)] == ["run_a/107"]


def test_helpers_for_addresses_and_elements():
    assert without_site("see http://localhost:7790/admin/sales/order/ now") == (
        "see /sales/order/ now"
    )
    assert without_site("http://localhost:7780/admin") == ""
    assert element_on_page(GRID, 10) == 'link " SALES"'
    assert element_on_page(GRID, 999) == ""
    assert element_on_page(GRID, None) == ""


# -- skills -----------------------------------------------------------------

CODE = """def run(order_number):
    goto("/sales/order/")
    check(url="^/sales/order/?$")
    click(role="link", name="View", row=order_number)
    check(text="Order # " + order_number)
    click(role="button", name="Cancel")
    check(text="You canceled the order.")
"""


def raw_skill(**changes):
    raw = {
        "name": "cancel-order",
        "description": "Cancel an order given its number.",
        "url_pattern": "^/",
        "params": [
            {
                "name": "order_number",
                "type": "string",
                "description": "As the grid shows it",
                "slot": "id",
            }
        ],
        "required_elements": [],
        "preconditions": [{"text": None, "url": "^/", "role": None, "name": None,
                           "row": None, "section": None, "why": "any page of the site"}],
        "steps": '1. Open the order grid.\n2. Click "View" in the row of the order.\n'
        '3. Click "Cancel" and confirm. Check: "You canceled the order." is shown.',
        "code": CODE,
        "source_args": [{"name": "order_number", "value": '"000000302"'}],
        "other_args": [
            {"args": [{"name": "order_number", "value": '"000000299"'}], "seen": "the grid"}
        ],
    }  # fmt: skip
    return {**raw, **changes}


@pytest.fixture
def cancel(learn_runs):
    return next(e for e in episodes(learn_runs) if e.key == "run_b/470")


def test_a_candidate_in_form_keeps_its_steps_its_code_and_its_test_values(cancel):
    candidate = check_candidate(raw_skill(), cancel)

    assert candidate.rejected == []
    assert candidate.skill.name == "cancel-order"
    assert candidate.skill.meta.version == 1
    # The stored skill is guidance; code is kept apart until it has been verified.
    assert candidate.skill.code is None
    assert candidate.code == CODE
    assert candidate.source_args == {"order_number": "000000302"}
    assert candidate.other_args == [{"order_number": "000000299"}]


@pytest.mark.parametrize(
    ("changes", "why"),
    [
        ({"name": "Cancel Order"}, "not in form"),
        ({"steps": "Cancel it."}, "numbered steps"),
        ({"url_pattern": "^/sales/(order"}, "regular expression"),
        ({"source_args": []}, "source_args do not fit the parameters"),
        (
            {"steps": '1. Open the grid.\n2. Click "View" in the row of order 000000302.'},
            "the steps carry literal values of the task: 000000302",
        ),
    ],
)
def test_a_skill_that_is_not_in_form_or_carries_a_task_value_is_rejected(cancel, changes, why):
    candidate = check_candidate(raw_skill(**changes), cancel)

    assert candidate.skill is None
    assert why in candidate.rejected[0]


@pytest.mark.parametrize(
    ("code", "why"),
    [
        ("import os\n" + CODE, "not allowed"),
        (CODE.replace('    check(text="You canceled the order.")\n', ""), "needs a check"),
        (CODE.replace("order_number", "number"), "SKILL.md declares"),
        (CODE.replace("row=order_number", 'row="000000302"'), "literal values of the task"),
    ],
)
def test_code_that_breaks_a_rule_leaves_the_skill_as_guidance(cancel, code, why):
    candidate = check_candidate(raw_skill(code=code), cancel)

    assert candidate.skill is not None
    assert candidate.code is None
    assert any(why in problem for problem in candidate.code_problems)


def test_a_skill_may_come_without_code(cancel):
    candidate = check_candidate(raw_skill(code=None), cancel)

    assert candidate.skill is not None
    assert candidate.code is None
    assert candidate.notes == ["the model wrote no code"]


@pytest.mark.parametrize(
    ("value", "excluded", "why"),
    [
        ('"000000302"', [], "the same as the episode's values"),
        ('"000000777"', [], "not shown on the episode's pages"),
        ('"000000299"', ["Cancel order 000000299"], "a held-out task uses 000000299"),
        ("299", [], "must be a string"),
    ],
)
def test_other_values_must_be_on_the_episodes_pages_and_not_in_a_held_out_task(
    cancel, value, excluded, why
):
    other = [{"args": [{"name": "order_number", "value": value}], "seen": "the grid"}]

    candidate = check_candidate(raw_skill(other_args=other), cancel, excluded)

    assert candidate.other_args == []
    assert why in candidate.notes[-1]


def test_task_literals_are_long_numbers_and_quoted_text():
    assert task_literals('Notify "Jane Doe" in order 000000302 by $5') == ["000000302", "Jane Doe"]


def test_a_refused_answer_gets_one_second_try_with_the_reasons(tmp_path, cancel):
    bad = raw_skill(code="import os\n" + CODE)
    llm, provider, _, _ = make_client(
        tmp_path, [reply(tool_call("save_skill", bad)), reply(tool_call("save_skill", raw_skill()))]
    )

    candidate = induce_skill(llm, cancel)

    assert (candidate.attempts, candidate.code) == (2, CODE)
    assert "first attempt refused" in candidate.notes[-1]
    second_prompt = provider.calls[1]["messages"][0].content
    assert "It was refused for these reasons" in second_prompt
    assert "not allowed" in second_prompt
    # The call is told the episode succeeded and sees no evaluator detail.
    assert "scored successful" in provider.calls[0]["system"]
    assert provider.calls[0]["tools"] == ["save_skill"]


def test_a_second_try_that_is_worse_does_not_replace_the_first(tmp_path, cancel):
    first = raw_skill(code="import os\n" + CODE)
    llm, _, _, _ = make_client(
        tmp_path,
        [
            reply(tool_call("save_skill", first)),
            reply(tool_call("save_skill", raw_skill(name="Bad Name"))),
        ],
    )

    candidate = induce_skill(llm, cancel)

    assert candidate.skill.name == "cancel-order"
    assert candidate.code is None
    assert "second attempt refused" in candidate.notes[-1]


def test_a_reply_without_the_tool_call_is_an_error(tmp_path, cancel):
    llm, _, _, _ = make_client(tmp_path, [reply(text="Here is a skill...")])

    with pytest.raises(BuildError, match="did not call save_skill"):
        induce_skill(llm, cancel)


# -- site facts and lessons ---------------------------------------------------


def test_facts_are_kept_short_general_and_with_a_valid_pattern(tmp_path, cancel):
    facts = [
        {"text": "Orders are listed under SALES > Orders.", "url_pattern": "^/sales/order/"},
        {"text": "Order 000000302 belongs to Jane Doe.", "url_pattern": "^/sales/order/"},
        {"text": "x" * 301, "url_pattern": "^/"},
        {"text": "The grid can be filtered.", "url_pattern": "^/sales/(order"},
        {"text": "A fifth fact is one too many.", "url_pattern": "^/"},
    ]
    llm, provider, _, _ = make_client(tmp_path, [reply(call("save_facts", facts=facts))])

    kept, dropped = extract_facts(llm, cancel)

    assert kept == [
        Note("Orders are listed under SALES > Orders.", "^/sales/order/", (cancel.source(),))
    ]
    assert len(dropped) == 3
    assert "carries a literal value of the task" in dropped[0]
    assert "scored successful" in provider.calls[0]["system"]


def test_reflection_sees_the_trace_and_only_that_the_episode_failed(tmp_path, learn_runs):
    failed = failures(episodes(learn_runs))[0]
    lessons = [
        {"text": "On the order grid, filter by status first.", "url_pattern": "^/sales/order/"}
    ]
    llm, provider, _, _ = make_client(tmp_path, [reply(call("save_lessons", lessons=lessons))])

    kept, dropped = reflect(llm, failed)

    assert [note.text for note in kept] == ["On the order grid, filter by status first."]
    assert dropped == []
    system = provider.calls[0]["system"]
    assert "scored as failed" in system
    assert "not told what the right result is" in system
    assert provider.calls[0]["messages"][0].content == failed.render()


def test_notes_that_repeat_are_merged_and_the_rest_stay_word_for_word(tmp_path):
    notes = {
        "fact-001": Note("Orders are under SALES > Orders.", "^/sales/order/", ({"task_id": 1},)),
        "fact-002": Note("The order grid is at SALES, Orders.", "^/sales/", ({"task_id": 2},)),
        "fact-003": Note("Reports need a date range.", "^/reports/", ({"task_id": 3},)),
        "fact-004": Note("Reviews are under MARKETING.", "^/review/", ({"task_id": 4},)),
    }
    merged = [
        {"text": "Orders are listed under SALES > Orders.", "url_pattern": "^/sales/",
         "from": ["fact-001", "fact-002"]},
        {"text": "Reports always need dates!", "url_pattern": "^/reports/", "from": ["fact-003"]},
        {"text": "Made up.", "url_pattern": "^/", "from": ["fact-999"]},
    ]  # fmt: skip
    llm, _, _, _ = make_client(tmp_path, [reply(call("merge_items", items=merged))])

    result = merge_notes(llm, notes)

    assert [(note.text, ids) for note, ids in result] == [
        ("Orders are listed under SALES > Orders.", ["fact-001", "fact-002"]),
        # A note that stands only for itself is not reworded by the merge.
        ("Reports need a date range.", ["fact-003"]),
        # A note the model left out is kept as it was.
        ("Reviews are under MARKETING.", ["fact-004"]),
    ]
    assert result[0][0].sources == ({"task_id": 1}, {"task_id": 2})


# -- the store ----------------------------------------------------------------


def test_a_build_is_written_from_learn_runs_and_can_be_opened_read_only(tmp_path, learn_runs):
    replies = [
        reply(tool_call("save_skill", raw_skill())),
        reply(call("save_facts", facts=[
            {"text": "Orders are under SALES > Orders.", "url_pattern": "^/sales/order/"},
            {"text": "The order grid is at SALES, Orders.", "url_pattern": "^/sales/"},
        ])),
        reply(call("merge_items", items=[
            {"text": "Orders are listed under SALES > Orders.", "url_pattern": "^/sales/",
             "from": ["fact-001", "fact-002"]},
        ])),
        reply(call("save_lessons", lessons=[
            {"text": "On the order grid, filter by status first.", "url_pattern": "^/sales/order/"},
        ])),
    ]  # fmt: skip
    llm, provider, _, _ = make_client(tmp_path / "llm", replies)
    config = BuildConfig(name="t", runs=["run_a", "run_b"])
    build = learn_runs / "memory_store" / "2026-01-01_t"

    induce(config, learn_runs, llm, build).close()
    store = MemoryStore.open(build)

    skills = store.skills()
    assert list(skills) == ["cancel-order"]
    assert skills["cancel-order"].code is None  # guidance until the code is verified
    assert (build / "candidates" / "cancel-order" / "skill.py").read_text() == CODE
    assert (build / "skills" / "cancel-order" / "v1" / "SKILL.md").is_file()
    facts = store.items("site_fact")
    assert [(item.label, item.text) for item in facts] == [
        ("fact-001@v2", "Orders are listed under SALES > Orders.")
    ]
    assert [(i.label, i.status) for i in store.items("site_fact", active_only=False)] == [
        ("fact-001@v1", "retired"), ("fact-002@v1", "retired"), ("fact-001@v2", "active"),
    ]  # fmt: skip
    assert [item.text for item in store.items("lesson")] == [
        "On the order grid, filter by status first."
    ]
    provenance = store.provenance()
    assert provenance["skill_and_fact_sources"] == [
        {"run": "run_b", "task_id": 470, "template_id": 257}
    ]
    assert provenance["lesson_sources"] == [{"run": "run_a", "task_id": 107, "template_id": 270}]
    assert provenance["templates_without_a_successful_episode"] == [270]
    assert provenance["model"] == "fake-model"
    manifest = json.loads((build / "manifest.json").read_text())
    assert len(manifest["items"]) == 5
    assert all(len(item["sha256"]) == 64 for item in manifest["items"])
    events = [record["event"] for record in read_log(build)]
    assert events == ["sources", "skill_candidate", "facts", "merged", "lessons", "induced"]
    # Frozen: a run cannot write to the memory it is measured with.
    with pytest.raises(StoreError, match="read-only"):
        store.add("lesson", "lesson-009", "x", "^/", [])
    with pytest.raises(StoreError, match="read-only"):
        store.count_use("skill", "cancel-order", 1, True)
    assert len(provider.calls) == 4


def test_versions_are_added_and_retired_never_overwritten(tmp_path):
    store = MemoryStore.create(tmp_path / "build", {"name": "t"})
    store.add("lesson", "lesson-001", "First wording.", "^/a/", [{"task_id": 1}])
    store.add("lesson", "lesson-001", "Better wording.", "^/a/", [{"task_id": 1}], note="reworded")
    store.add("lesson", "lesson-002", "Another.", "^/b/", [])
    store.retire("lesson", "lesson-002", "did not hold")
    store.count_use("lesson", "lesson-001", 2, success=True)
    store.count_use("lesson", "lesson-001", 2, success=False)

    everything = store.items("lesson", active_only=False)

    assert [(i.label, i.status, i.text) for i in everything] == [
        ("lesson-001@v1", "retired", "First wording."),
        ("lesson-001@v2", "active", "Better wording."),
        ("lesson-002@v1", "retired", "Another."),
    ]
    assert "[superseded by v2]" in everything[0].note
    assert "[retired: did not hold]" in everything[2].note
    assert (everything[1].use_count, everything[1].success_count) == (2, 1)
    with pytest.raises(StoreError, match="no active lesson lesson-002"):
        store.retire("lesson", "lesson-002", "again")
    with pytest.raises(StoreError, match="a new build gets a new directory"):
        MemoryStore.create(tmp_path / "build", {})
    with pytest.raises(StoreError, match="is not a memory build"):
        MemoryStore.open(tmp_path / "nothing")


def test_a_skill_version_goes_into_its_own_folder(tmp_path, cancel):
    store = MemoryStore.create(tmp_path / "build", {"name": "t"})
    guidance = check_candidate(raw_skill(), cancel).skill
    store.add_skill(guidance, cancel.source())
    from dataclasses import replace

    verified = replace(guidance, meta=guidance.meta.model_copy(update={"version": 2}), code=CODE)

    with pytest.raises(StoreError, match="the next version is 2, not 1"):
        store.add_skill(guidance, cancel.source())
    store.add_skill(verified, cancel.source(), note="code verified")

    assert store.skills()["cancel-order"].code == CODE
    assert (tmp_path / "build/skills/cancel-order/v1/SKILL.md").is_file()
    assert not (tmp_path / "build/skills/cancel-order/v1/skill.py").exists()
    assert (tmp_path / "build/skills/cancel-order/v2/skill.py").is_file()
    assert [(i.label, i.status) for i in store.items("skill", active_only=False)] == [
        ("cancel-order@v1", "retired"), ("cancel-order@v2", "active"),
    ]  # fmt: skip


def test_field_names_of_the_answer_are_not_values_of_the_task():
    intent = (
        "Get the customer name and email with phone number +1 2058812302. Return a list of "
        'objects with keys "name" and "email".'
    )

    # Before this rule a skill was refused for saying "name" and "email".
    assert task_literals(intent) == ["2058812302"]
    assert task_literals('Change the title of "404 Not Found" to "Oops"') == [
        "404",
        "404 Not Found",
        "Oops",
    ]


def test_a_failed_model_call_costs_one_item_not_the_build(tmp_path, cancel):
    from browser_agent.harness.llm import ModelError

    llm, _, _, _ = make_client(tmp_path, [ModelError("request rejected (400)", status_code=400)])

    with pytest.raises(BuildError, match="the model call failed: request rejected"):
        extract_facts(llm, cancel)


# -- template slots -----------------------------------------------------------


def test_slots_are_what_a_task_puts_into_its_template():
    assert match_slots("Cancel order {{id}}", "Cancel order 302") == {"id": "302"}
    assert match_slots(
        "Show the {{report}} for {{time_span}} (today is March 15, 2023).",
        "Show the sales order report for for last months (today is March 15, 2023).",
    ) == {"report": "sales order report", "time_span": "for last months"}
    # A slot may be empty, here the one for the layout of the answer.
    assert match_slots(
        "Get the {{attribute}} of the {{status}} order.{{retrieved_data_format_spec}}",
        "Get the customer email of the most recent cancelled order.",
    ) == {
        "attribute": "customer email",
        "status": "most recent cancelled",
        "retrieved_data_format_spec": "",
    }
    assert match_slots("Cancel order {{id}}", "Delete order 302") is None
    assert match_slots("", "Cancel order 302") is None


def test_the_values_of_a_task_come_from_its_slots_not_from_its_answer_format(learn_runs):
    entry = {
        "task_id": 208, "template_id": 364, "split": "learn",
        "intent": "Get the customer name and email with phone number +1 2058812302. "
        'Return a list of objects with keys "name" and "email".',
        "intent_template": "Get the customer name and email with phone number {{PhoneNum}}. "
        "{{retrieved_data_format_spec}}.",
    }  # fmt: skip
    write_run(learn_runs, "run_c", [(208, 364, True, CANCEL_STEPS)])

    episode = load_episodes(learn_runs / "results", ["run_c"], [entry])[0]

    assert episode.value_slots() == {"PhoneNum": "+1 2058812302"}
    # "name" and "email" are fields of the answer, not values of the task.
    assert episode.literals() == ["+1 2058812302", "2058812302"]


@pytest.mark.parametrize(
    ("value", "quoted", "instance"),
    [
        ("302", False, True),
        ("March 31, 2022", False, True),
        ("Jane Doe", False, True),
        ("sorry we are out of stock, please reorder", False, True),
        ("disappointed", True, True),
        ("orders", False, False),
        ("Reduce", False, False),
        ("so far", False, False),
        ("customer email", False, False),
        ("$5", False, False),
    ],
)
def test_a_value_either_names_one_thing_or_a_kind_of_thing(value, quoted, instance):
    assert names_an_instance(value, quoted) is instance


def test_only_learn_tasks_get_their_template(learn_runs):
    learn, held_out = learn_entries(learn_runs, BuildConfig(name="t", runs=[]))

    assert [(e["task_id"], e["intent_template"]) for e in learn] == [
        (470, "Cancel order {{id}}"),
        (107, 'Count orders of "{{customer}}" in {{year}}'),
    ]
    assert held_out == ["Cancel order 299"]


def test_the_induction_call_is_shown_the_template_and_the_slots(tmp_path, cancel):
    llm, provider, _, _ = make_client(tmp_path, [reply(tool_call("save_skill", raw_skill()))])

    induce_skill(llm, cancel)

    prompt = provider.calls[0]["messages"][0].content
    assert "Task template: Cancel order {{id}}" in prompt
    assert "Slots in this task: id = '302'" in prompt
    assert "Every slot is carried by at least one parameter" in provider.calls[0]["system"]


def test_a_skill_that_leaves_a_slot_without_a_parameter_gets_no_code(cancel):
    """count-shop-reviews of the first build: no parameter for {{time}}, so on the next
    task of the template it would have answered for the wrong period."""
    no_slot = raw_skill()
    no_slot["params"][0]["slot"] = None

    candidate = check_candidate(no_slot, cancel)

    assert candidate.skill is not None  # kept as guidance, for the model to read
    assert candidate.code is None
    assert candidate.code_problems == [
        "no parameter carries the template's slot {{id}}; every slot must be a parameter"
    ]
    assert candidate.param_slots == {"order_number": None}


def test_a_refused_slot_gets_a_second_try(tmp_path, cancel):
    no_slot = raw_skill()
    no_slot["params"][0]["slot"] = None
    llm, provider, _, _ = make_client(
        tmp_path,
        [reply(tool_call("save_skill", no_slot)), reply(tool_call("save_skill", raw_skill()))],
    )

    candidate = induce_skill(llm, cancel)

    assert candidate.code == CODE
    assert candidate.param_slots == {"order_number": "id"}
    assert "every slot must be a parameter" in provider.calls[1]["messages"][0].content


# -- a derived build: the site facts merged again -----------------------------


def test_facts_are_merged_again_in_a_derived_build_and_the_source_stays_as_it_was(tmp_path):
    from browser_agent.memory.pipeline import BuildLog, derive_build, remerge_facts

    source = MemoryStore.create(tmp_path / "memory_store" / "2026-01-01_a", {"name": "a"})
    source.add(
        "site_fact",
        "fact-001",
        "The Orders report is under Reports > Sales.",
        "^/reports/",
        [{"task_id": 1}],
    )
    source.add(
        "site_fact",
        "fact-002",
        "Reports > Sales > Orders opens the Orders report.",
        "^/reports/",
        [{"task_id": 2}],
    )
    source.add(
        "site_fact", "fact-003", "Reviews are under MARKETING.", "^/review/", [{"task_id": 3}]
    )
    source.add("lesson", "lesson-001", "Filter the grid first.", "^/sales/", [{"task_id": 4}])
    source.write_manifest()
    source.close()
    merged = [
        {"text": "The Orders report is at Reports > Sales > Orders.", "url_pattern": "^/reports/",
         "from": ["fact-001", "fact-002"]},
        {"text": "Reviews are under MARKETING.", "url_pattern": "^/review/", "from": ["fact-003"]},
    ]  # fmt: skip
    llm, provider, _, _ = make_client(tmp_path / "llm", [reply(call("merge_items", items=merged))])
    target = tmp_path / "memory_store" / "2026-01-02_b"

    store = derive_build(tmp_path / "memory_store" / "2026-01-01_a", target, "facts merged", "abc")
    fits = remerge_facts(store, llm, BuildLog(target / "build_log.jsonl", echo=lambda line: None))
    store.close()

    assert fits
    derived = MemoryStore.open(target)
    assert [(i.label, i.text) for i in derived.items("site_fact")] == [
        ("fact-003@v1", "Reviews are under MARKETING."),
        ("fact-001@v2", "The Orders report is at Reports > Sales > Orders."),
    ]
    assert derived.items("site_fact")[1].source == [{"task_id": 1}, {"task_id": 2}]
    # Lessons are untouched, and the build says where it came from.
    assert [i.label for i in derived.items("lesson")] == ["lesson-001@v1"]
    assert derived.provenance()["derivations"][0]["from"] == "2026-01-01_a"
    assert derived.provenance()["name"] == "b"
    # The build it was derived from holds what it held before.
    original = MemoryStore.open(tmp_path / "memory_store" / "2026-01-01_a")
    assert [i.label for i in original.items("site_fact")] == [
        "fact-001@v1", "fact-002@v1", "fact-003@v1",
    ]  # fmt: skip
    assert "says each thing" in provider.calls[0]["system"]
    assert len(provider.calls) == 1  # everything fits after one pass
    with pytest.raises(FileExistsError):
        derive_build(tmp_path / "memory_store" / "2026-01-01_a", target, "again", "abc")
