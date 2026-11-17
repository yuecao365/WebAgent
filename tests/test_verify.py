"""The gate, and the verification of candidate skill code, without a site or a model."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from browser_agent.browser.observation import Observation
from browser_agent.harness.llm import ToolCall
from browser_agent.memory.episodes import Episode
from browser_agent.memory.gate import check_gate
from browser_agent.memory.pipeline import BuildLog
from browser_agent.memory.skill import Skill, parse_skill_md
from browser_agent.memory.verify import Verifier, leaves, same_values

from fakes import FakeSession, FakeSite, load_fixture, make_client, reply

BASE = "http://site.test/admin"
GRID = f"{BASE}/sales/order/"
ORDER = f"{BASE}/sales/order/view/order_id/299/"
VIEW_299 = 1842

SKILL_MD = """---
name: read-order-total
description: Read the grand total of an order.
version: 1
params:
  order_number: {type: string}
url_pattern: "^/sales/order/?$"
required_elements:
  - {role: link, name: View, row: "{order_number}"}
preconditions:
  - {role: button, name: Filters, why: the order grid is loaded}
  - {text: "{order_number}"}
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
ARGS = {"order_number": "000000299"}


def skill(md=SKILL_MD, code=CODE):
    meta, body = parse_skill_md(md)
    return Skill(meta, body, code)


def page(url=GRID, fixture="ax_orders_grid.json"):
    return Observation(url=url, title="T", nodes=load_fixture(fixture))


# -- the gate -----------------------------------------------------------------


def test_the_gate_passes_when_every_check_holds():
    assert check_gate(skill(), ARGS, page(), BASE).passed


def test_a_skill_without_code_never_passes_the_gate():
    result = check_gate(skill(code=None), ARGS, page(), BASE)

    assert (result.passed, result.check) == (False, "no_code")


def test_the_address_must_match_the_url_pattern():
    result = check_gate(skill(), ARGS, page(url=ORDER), BASE)

    assert (result.passed, result.check) == (False, "url_pattern")
    assert "/sales/order/view/order_id/299/ does not match" in result.detail


@pytest.mark.parametrize(
    ("args", "found"),
    [({"order_number": "000009999"}, "0 elements"), ({"order_number": "Pending"}, "2 elements")],
)
def test_a_required_element_must_resolve_to_exactly_one(args, found):
    result = check_gate(skill(), args, page(), BASE)

    assert (result.passed, result.check) == (False, "required_element")
    assert result.detail.startswith(found)
    assert "where exactly one is needed" in result.detail


def test_every_precondition_must_hold():
    no_button = SKILL_MD.replace("name: Filters", "name: Unfilter")
    no_text = SKILL_MD.replace('text: "{order_number}"', 'text: "Archived orders"')
    other_url = SKILL_MD.replace('- {text: "{order_number}"}', '- {url: "^/sales/archive/"}')

    for changed, why in [
        (no_button, '0 elements match button "Unfilter"'),
        (no_text, 'the page does not show "Archived orders"'),
        (other_url, "does not match ^/sales/archive/"),
    ]:
        result = check_gate(skill(md=changed), ARGS, page(), BASE)
        assert (result.passed, result.check) == (False, "precondition")
        assert why in result.detail


def test_checks_are_made_in_order_and_the_first_failure_is_reported():
    # Wrong page and missing element: the address is what is reported.
    result = check_gate(skill(), {"order_number": "000009999"}, page(url=ORDER), BASE)

    assert result.check == "url_pattern"


def test_a_placeholder_without_a_value_fails_the_gate_instead_of_raising():
    result = check_gate(skill(), {}, page(), BASE)

    assert (result.passed, result.check) == (False, "required_element")
    assert "no value for the placeholder {order_number}" in result.detail


# -- verification -------------------------------------------------------------

GOTO_CODE = (
    "def run(order_number):\n"
    '    goto("/sales/order/")\n'
    '    check(role="button", name="Filters")\n' + CODE.split("\n", 1)[1]
)
ANYWHERE = (
    SKILL_MD.replace('url_pattern: "^/sales/order/?$"', 'url_pattern: "^/"').split(
        "required_elements:"
    )[0]
    + "---\n\n1. Open the grid and the order.\n2. Read the grand total.\n"
)


def episode(task_type="retrieve", answer=("$219.40",), state_changing=False):
    return Episode(
        run="learn_x",
        task_id=7,
        template_id=3,
        task_type=task_type,
        state_changing=state_changing,
        intent="What is the grand total of order 299?",
        success=True,
        finish_reason="finished",
        steps=[],
        answer={"task_type": task_type.upper(), "retrieved_data": list(answer)},
    )


def verdict_reply(passed, reason="looks right"):
    arguments = {"passed": passed, "reason": reason}
    return reply(ToolCall("call_v", "verdict", arguments, json.dumps(arguments)))


def setup(tmp_path, replies, site=None):
    session = FakeSession()
    session.redirects[BASE] = f"{BASE}/admin/dashboard/"
    session.pages = {
        GRID: load_fixture("ax_orders_grid.json"),
        ORDER: load_fixture("ax_order_view.json"),
    }
    session.element(VIEW_299, tag="a")
    session.links[VIEW_299] = ORDER
    site = site or FakeSite()
    llm, provider, _, _ = make_client(tmp_path / "llm", replies)
    log = BuildLog(tmp_path / "log.jsonl", echo=lambda line: None)
    (tmp_path / "work").mkdir()
    return Verifier(site, session, llm, log, tmp_path / "work"), provider, site


def test_code_is_kept_when_the_original_and_the_other_replays_pass(tmp_path):
    verifier, provider, site = setup(tmp_path, [verdict_reply(True), verdict_reply(True)])

    verdict = verifier.verify(
        skill(ANYWHERE, GOTO_CODE), episode(), ARGS, [{"order_number": "000000299"}]
    )

    assert verdict.code_kept
    assert verdict.why == "all 2 replays passed"
    original, other = verdict.replays
    assert (original.kind, original.value, original.reproduced) == ("original", "$219.40", True)
    assert original.final_path == "/sales/order/view/order_id/299/"
    assert (other.kind, other.reproduced, other.verifier_passed) == ("other", None, True)
    # The verifier has its own context: the skill, the values, the result, the last page.
    prompt = provider.calls[0]["messages"][0].content
    assert "name: read-order-total" in prompt
    assert 'Parameter values of this run: {"order_number": "000000299"}' in prompt
    assert 'Value the code handed back: "$219.40"' in prompt
    assert "Grand Total" in prompt
    assert "What is the grand total of order 299?" not in prompt
    assert "not told what the right result is" in provider.calls[0]["system"]
    # A skill that only reads needs no reset between replays.
    assert site.site_resets == 0


def test_an_answer_shaped_differently_but_holding_the_same_values_is_the_same(tmp_path):
    verifier, _, _ = setup(tmp_path, [verdict_reply(True)])

    verdict = verifier.verify(skill(ANYWHERE, GOTO_CODE), episode(answer=(219.4,)), ARGS, [])

    assert verdict.code_kept


def test_a_replay_that_returns_something_else_than_the_episode_fails(tmp_path):
    verifier, provider, _ = setup(tmp_path, [])

    verdict = verifier.verify(skill(ANYWHERE, GOTO_CODE), episode(answer=("$210.00",)), ARGS, [])

    assert not verdict.code_kept
    assert "did not reproduce the episode's outcome" in verdict.why
    assert '"$219.40"' in verdict.why
    # Settled without asking the verifier.
    assert provider.calls == []


def test_the_verifier_can_fail_a_replay_that_ran_through(tmp_path):
    verifier, _, _ = setup(tmp_path, [verdict_reply(False, "the page shows another order")])

    verdict = verifier.verify(skill(ANYWHERE, GOTO_CODE), episode(), ARGS, [])

    assert not verdict.code_kept
    assert verdict.why == "the original replay failed: the verifier: the page shows another order"


def test_a_step_or_check_that_fails_in_a_replay_fails_it(tmp_path):
    verifier, provider, _ = setup(tmp_path, [verdict_reply(True)])

    verdict = verifier.verify(
        skill(ANYWHERE, GOTO_CODE), episode(), ARGS, [{"order_number": "000009999"}]
    )

    assert not verdict.code_kept
    assert verdict.why.startswith("the other replay failed: step 3 click(")
    assert "no element matches" in verdict.why
    assert len(provider.calls) == 1


def test_a_replay_the_gate_rejects_on_the_start_page_fails(tmp_path):
    verifier, _, _ = setup(tmp_path, [])

    # This skill starts on the order grid, but the task starts on the dashboard.
    verdict = verifier.verify(skill(), episode(), ARGS, [])

    assert not verdict.code_kept
    assert "the gate rejects it on the task's start page" in verdict.why


def test_a_skill_that_changes_data_is_scored_by_the_evaluator_and_the_site_is_reset(tmp_path):
    verifier, _, site = setup(tmp_path, [verdict_reply(True), verdict_reply(True)])
    changing = episode(task_type="mutate", state_changing=True)

    verdict = verifier.verify(
        skill(ANYWHERE, GOTO_CODE), changing, ARGS, [{"order_number": "000000299"}]
    )

    assert verdict.code_kept
    assert verdict.replays[0].reproduced_how == "the official evaluator scored the replay True"
    # The evaluator got the answer a finished task would give, and only for the original.
    assert site.scored == [
        (7, {"task_type": "MUTATE", "status": "SUCCESS", "retrieved_data": None,
             "error_details": None})
    ]  # fmt: skip
    # Reset before each of the two replays; the caller resets once more at the end.
    assert site.site_resets == 2
    assert verifier.dirty


def test_a_replay_the_evaluator_scores_failed_drops_the_code(tmp_path):
    site = FakeSite()
    site.evaluation = False
    verifier, provider, _ = setup(tmp_path, [], site=site)

    verdict = verifier.verify(skill(ANYWHERE, GOTO_CODE), episode(task_type="navigate"), ARGS, [])

    assert not verdict.code_kept
    assert "the official evaluator scored the replay False" in verdict.why
    assert provider.calls == []


def test_values_are_compared_by_what_they_hold():
    assert leaves([{"name": "Jane Doe", "email": "J@X.com"}]) == ["j@x.com", "jane doe"]
    assert same_values("$1,219.40", [1219.4])
    assert same_values(["351"], [351])
    assert same_values({"a": [True]}, ["true"])
    assert not same_values("351", [352])
    assert not same_values(None, [])
    assert not same_values([], [])
    assert same_values(replace(episode(), answer=None).answer, None) is False
