"""The subset builder, on made-up tasks and on the installed dataset."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from browser_agent.eval.webarena import (
    build_subset,
    dataset_tasks,
    expected_answer,
    is_state_changing,
    load_subset,
    scorable,
    unexpected_writes,
)

ROOT = Path(__file__).resolve().parents[1]
WORDINGS = {
    1: "Get the best-selling product in {{period}}",
    2: "Cancel order {{id}}",
    3: "Show the {{report}} report for {{period}}",
    4: "How many reviews mention {{term}}?",
    5: "Disable {{product}} from the site",
    6: "Get the best-selling product in {{quarter}}",
}


def distinct_wording(template):
    """A wording unlike that of any other template number."""
    return " ".join(chr(97 + (template * step) % 26) * 6 for step in (1, 3, 7, 11))


def task(task_id, template, task_type="retrieve", status="SUCCESS", sites=("shopping_admin",)):
    return {
        "task_id": task_id,
        "intent_template_id": template,
        "sites": list(sites),
        "intent": f"intent {task_id}",
        "intent_template": WORDINGS.get(template, distinct_wording(template)),
        "eval": [
            {"evaluator": "NetworkEventEvaluator", "expected": {"url": "x"}},
            {
                "evaluator": "AgentResponseEvaluator",
                "expected": {"task_type": task_type, "status": status},
            },
        ],
    }


def template(template_id, first_id, count, task_type="retrieve"):
    return [task(first_id + n, template_id, task_type) for n in range(count)]


def test_first_task_of_each_template_is_for_learning():
    tasks = template(1, 10, 5) + template(2, 20, 4, "mutate")

    subset = build_subset(tasks, {"retrieve": 1, "mutate": 1}, per_template=4)

    assert [(t["task_id"], t["split"]) for t in subset["tasks"]] == [
        (10, "learn"), (11, "test"), (12, "test"), (13, "test"),
        (20, "learn"), (21, "test"), (22, "test"), (23, "test"),
    ]  # fmt: skip
    assert subset["templates"][0] == {
        "template_id": 1,
        "task_type": "retrieve",
        "intent_template": WORDINGS[1],
        "task_ids": [10, 11, 12, 13],
    }


def test_tasks_are_taken_in_id_order_whatever_the_input_order():
    tasks = list(reversed(template(1, 10, 4)))

    subset = build_subset(tasks, {"retrieve": 1}, per_template=3)

    assert [t["task_id"] for t in subset["tasks"]] == [10, 11, 12]


def test_tasks_expected_to_fail_and_other_sites_are_left_out():
    tasks = [
        task(10, 1, status="NOT_FOUND_ERROR"),
        *template(1, 11, 3),
        task(14, 1, sites=("shopping_admin", "map")),
        *template(7, 70, 4, "mutate"),
    ]
    for entry in tasks[-4:]:
        entry["sites"] = ["gitlab"]

    subset = build_subset(tasks, {"retrieve": 1}, per_template=3)

    assert [t["task_id"] for t in subset["tasks"]] == [11, 12, 13]


def test_small_and_mixed_templates_are_not_candidates():
    small = template(1, 10, 2)
    mixed = [*template(2, 20, 2), *template(2, 22, 2, "mutate")]

    with pytest.raises(ValueError, match="only 0 of 1 retrieve templates"):
        build_subset(small + mixed, {"retrieve": 1}, per_template=3)


def test_near_duplicate_wordings_are_not_both_taken():
    tasks = template(1, 10, 3) + template(6, 60, 3) + template(4, 40, 3)

    subset = build_subset(tasks, {"retrieve": 2}, per_template=3)

    chosen = {t["template_id"] for t in subset["templates"]}
    assert 4 in chosen
    assert len(chosen & {1, 6}) == 1


def test_selection_is_reproducible_and_depends_on_the_seed():
    tasks = [t for template_id in range(10, 30) for t in template(template_id, template_id * 10, 3)]

    def ids(seed):
        subset = build_subset(tasks, {"retrieve": 5}, per_template=3, seed=seed)
        return [t["template_id"] for t in subset["templates"]]

    assert ids(0) == ids(0)
    assert len({tuple(ids(seed)) for seed in range(5)}) > 1


def grid_navigation(task_id, template):
    """A navigate task that expects the grid's data request instead of a page load."""
    entry = task(task_id, template, "navigate")
    entry["eval"][0]["expected"]["url"] = "__SHOPPING_ADMIN__/mui/index/render/"
    return entry


def test_navigate_tasks_the_evaluator_cannot_pass_exclude_their_template():
    tasks = [grid_navigation(30 + n, 3) for n in range(3)] + template(9, 90, 3, "navigate")

    subset = build_subset(tasks, {"navigate": 1}, per_template=3)

    assert not scorable(tasks[0])
    assert scorable(tasks[-1])
    assert [t["template_id"] for t in subset["templates"]] == [9]
    assert subset["rules"]["unscorable_templates"] == [3]


def test_grid_requests_only_disqualify_navigate_tasks():
    entry = task(1, 1, "mutate")
    entry["eval"][0]["expected"]["url"] = "__SHOPPING_ADMIN__/mui/index/render/"

    assert scorable(entry)


def network_check(**expected):
    return {"evaluator": "NetworkEventEvaluator", "expected": {"url": "x", **expected}}


def test_a_task_checked_by_a_write_is_state_changing():
    answer_only = task(1, 1)
    answer_only["eval"] = answer_only["eval"][1:]
    navigation = task(2, 1, "navigate")
    navigation["eval"][0] = network_check(http_method="GET")
    default_method = task(3, 1, "navigate")
    default_method["eval"][0] = network_check(http_method=None)
    post = task(4, 1, "mutate")
    post["eval"][0] = network_check(http_method="POST")
    body = task(5, 1, "mutate")
    body["eval"][0] = network_check(post_data={"product[status]": "2"})

    kinds = [is_state_changing(t) for t in (answer_only, navigation, default_method, post, body)]

    assert kinds == [False, False, False, True, True]


def test_state_changing_tasks_across_the_site():
    tasks = [t for t in dataset_tasks() if list(t["sites"]) == ["shopping_admin"]]
    changing = {t["task_id"] for t in tasks if is_state_changing(t)}
    with_write_check = {
        t["task_id"]
        for t in tasks
        if any(
            e["evaluator"] == "NetworkEventEvaluator"
            and (
                (e["expected"].get("http_method") or "GET") != "GET"
                or e["expected"].get("post_data")
            )
            for e in t["eval"]
        )
    }

    assert len(tasks) == 182
    assert len(changing) == 78
    # Every task with a write check, plus the two that ask for a change the site refuses.
    assert changing - with_write_check == {491, 790}
    assert with_write_check <= changing


def test_unexpected_writes_ignore_saved_grid_filters():
    def request(method, url):
        return {"request": {"method": method, "url": url}}

    trace = [
        request("GET", "http://localhost:7780/admin/customer/index/"),
        request("POST", "http://localhost:7780/admin/mui/bookmark/save/"),
        request("POST", "http://localhost:7780/admin/sales/order/cancel/order_id/302/"),
    ]

    assert unexpected_writes(trace) == ["POST /admin/sales/order/cancel/order_id/302/"]
    assert unexpected_writes(trace[:2]) == []


def test_expected_answer_reads_the_response_evaluator():
    assert expected_answer(task(1, 1, "MUTATE", "SUCCESS")) == ("mutate", "SUCCESS")


# -- the checked-in subset ------------------------------------------------------


@pytest.fixture(scope="module")
def checked_in():
    return json.loads((ROOT / "configs" / "subset.json").read_text(encoding="utf-8"))


def test_checked_in_subset_has_the_agreed_shape(checked_in):
    tasks = checked_in["tasks"]
    per_template = Counter(t["template_id"] for t in tasks)

    assert 55 <= len(tasks) <= 65
    assert 15 <= len(per_template) <= 20
    assert all(3 <= count <= 5 for count in per_template.values())
    assert Counter(t["split"] for t in tasks)["learn"] == len(per_template)
    assert len({t["task_id"] for t in tasks}) == len(tasks)
    for template_id in per_template:
        members = [t for t in tasks if t["template_id"] == template_id]
        assert [t["split"] for t in members] == ["learn"] + ["test"] * (len(members) - 1)
        assert members[0]["task_id"] == min(t["task_id"] for t in members)


def test_checked_in_subset_is_what_the_builder_produces(checked_in):
    """Guards against the file and the rules drifting apart."""
    rules = checked_in["rules"]
    # Template 253 (order lists by status) expects a grid request the evaluator
    # never looks at for a navigate task.
    assert rules["unscorable_templates"] == [253]
    assert 253 not in {t["template_id"] for t in checked_in["templates"]}

    rebuilt = build_subset(
        dataset_tasks(),
        rules["quotas"],
        rules["per_template"],
        rules["seed"],
        rules["max_similarity"],
    )

    assert rebuilt == checked_in
    assert load_subset(ROOT / "configs" / "subset.json") == checked_in["tasks"]
