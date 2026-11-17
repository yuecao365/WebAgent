"""One run of a skill's code, against a fake browser showing saved pages."""

from __future__ import annotations

import pytest

from browser_agent.memory.skill import Skill, parse_skill_md
from browser_agent.memory.skill_api import run_skill_code, site_path

from fakes import FakeBrowser, load_fixture

BASE = "http://site.test/admin"
GRID = f"{BASE}/sales/order/"
ORDER = f"{BASE}/sales/order/view/order_id/299/"
REPORT = f"{BASE}/reports/report_sales/sales/"

# Refs in the saved trees.
VIEW_299 = 1842
COMMENT, NOTIFY, SUBMIT = 12605, 12606, 13908
PERIOD, FROM, TO, SHOW = 17060, 17061, 17062, 17792

FRONT = """---
name: {name}
description: A skill for the tests.
version: 1
params:
{params}
url_pattern: "^/"
time_limit_s: 60
---

1. Do the steps.
"""


def skill(code, **params):
    listed = "\n".join(f"  {key}: {{type: {kind}}}" for key, kind in params.items()) or "  {}"
    if not params:
        front = FRONT.replace("params:\n{params}\n", "")
        meta, body = parse_skill_md(front.format(name="test-skill"))
    else:
        meta, body = parse_skill_md(FRONT.format(name="test-skill", params=listed))
    return Skill(meta, body, code)


def site():
    """A fake browser on the order grid; "View" of order 299 leads to its page."""
    browser = FakeBrowser()
    browser.pages = {
        GRID: load_fixture("ax_orders_grid.json"),
        ORDER: load_fixture("ax_order_view.json"),
        REPORT: load_fixture("ax_sales_report.json"),
    }
    browser.url = GRID
    browser.element(VIEW_299, tag="a")
    browser.links[VIEW_299] = ORDER
    for ref in (COMMENT, FROM, TO):
        browser.element(ref, tag="input")
    for ref in (NOTIFY, SUBMIT, SHOW):
        browser.element(ref)
    browser.element(PERIOD, tag="select")
    browser.options[PERIOD] = ["Day", "Month", "Year"]
    return browser


def run(code, browser=None, clock=None, **args):
    kinds = {key: "boolean" if isinstance(value, bool) else "string" for key, value in args.items()}
    browser = browser or site()
    extra = {} if clock is None else {"clock": clock}
    outcome = run_skill_code(
        skill(code, **kinds), args, browser, BASE, ["http://site.test"], **extra
    )
    return outcome, browser


READ_TOTAL = """def run(order_number):
    goto("/sales/order/")
    check(url="^/sales/order/?$")
    click(role="link", name="View", row=order_number)
    check(text="Order # " + order_number)
    total = read(role="row", name="", row="Grand Total")
    return_value(total.replace("Grand Total", "").strip())
"""


def test_a_run_completes_every_step_and_hands_back_its_value():
    outcome, browser = run(READ_TOTAL, order_number="000000299")

    assert outcome.ok
    assert (outcome.returned, outcome.value) == (True, "$219.40")
    assert browser.url == ORDER
    assert [(step.call, step.ok) for step in outcome.steps] == [
        ("goto", True), ("check", True), ("click", True), ("check", True),
        ("read", True), ("return_value", True),
    ]  # fmt: skip
    assert outcome.steps[2].detail == "role='link', name='View', row='000000299'"
    assert outcome.failed_step is None


def test_a_check_that_does_not_hold_stops_the_run_at_that_step():
    """The order page opens, but it is not the order the skill was asked for."""
    wrong_number = READ_TOTAL.replace('"Order # " + order_number', '"Order # 000000300"')

    outcome, _ = run(wrong_number, order_number="000000299")

    assert not outcome.ok
    assert outcome.error == 'check failed: the page does not show "Order # 000000300"'
    assert (outcome.failed_step.number, outcome.failed_step.call) == (4, "check")
    # Nothing after the failed check ran.
    assert len(outcome.steps) == 4
    assert not outcome.returned


def test_a_locator_that_matches_nothing_or_several_stops_the_run():
    missing, _ = run(READ_TOTAL, order_number="000009999")
    several, _ = run(READ_TOTAL.replace(", row=order_number", ""), order_number="000000299")

    assert not missing.ok
    assert "no element matches" in missing.error
    assert missing.failed_step.call == "click"
    assert '13 elements match link "View", not one' in several.error


def test_a_form_is_filled_by_typing_and_selecting():
    code = """def run(start, end):
    goto("/reports/report_sales/sales/")
    check(role="button", name="Show Report")
    select(role="combobox", name="Period", option="Month")
    check(role="combobox", name="Period")
    type(role="textbox", name="From", text=start)
    type(role="textbox", name="To", text=end)
    click(role="button", name="Show Report")
    check(text="records found")
"""

    outcome, browser = run(code, start="01/01/2023", end="01/31/2023")

    assert outcome.ok, outcome.error
    assert browser.typed == ["01/01/2023", "01/31/2023"]
    assert outcome.steps[2].result == "Chose 'Month' in select [17060]."
    assert not outcome.returned


def test_an_option_the_dropdown_does_not_have_stops_the_run():
    code = """def run():
    goto("/reports/report_sales/sales/")
    check(role="button", name="Show Report")
    select(role="combobox", name="Period", option="Decade")
    check(role="combobox", name="Period")
"""

    outcome, _ = run(code)

    assert not outcome.ok
    assert "no option matching 'Decade'" in outcome.error


def test_a_field_that_does_not_take_what_was_typed_stops_the_run():
    code = """def run(start):
    goto("/reports/report_sales/sales/")
    check(role="button", name="Show Report")
    type(role="textbox", name="From", text=start)
"""
    browser = site()
    browser.masks[FROM] = "01/01/20"

    outcome, _ = run(code, browser=browser, start="01/01/2023")

    assert not outcome.ok
    assert outcome.error == "typed '01/01/2023', but the field reads '01/01/20'"


def test_a_table_is_read_as_rows():
    code = """def run(status):
    goto("/sales/order/")
    check(url="^/sales/order/?$")
    rows = read(role="table", name="")
    numbers = []
    for row in rows:
        if row[8] == status:
            numbers.append(row[1])
    return_value(numbers)
"""

    outcome, _ = run(code, status="Pending")

    assert outcome.ok, outcome.error
    assert outcome.value[:2] == ["000000299", "000000065"]


def test_goto_stays_inside_the_site():
    absolute = 'def run():\n    goto("http://example.com/")\n    check(text="x")\n'

    outcome, browser = run(absolute)

    assert not outcome.ok
    assert "relative to the site" in outcome.error
    assert browser.url == GRID


def test_a_step_that_opens_a_new_tab_stops_the_run():
    browser = site()
    browser.new_tab_links[VIEW_299] = f"{BASE}/catalog/product/edit/id/7/"

    outcome, _ = run(READ_TOTAL, browser=browser, order_number="000000299")

    assert not outcome.ok
    assert "the step opened a new tab at http://site.test/admin/catalog/product/edit/id/7/" in (
        outcome.error
    )
    # The tab was closed; the agent's tab is the one shown.
    assert browser.other_tabs == []


def test_the_time_limit_stops_the_run_before_the_next_step():
    ticks = iter(range(0, 10_000, 25))

    outcome, _ = run(READ_TOTAL, clock=lambda: next(ticks), order_number="000000299")

    assert not outcome.ok
    assert outcome.error == "the skill passed its time limit of 60 seconds"
    # Steps began at 25 and 50 seconds; the third found the limit passed.
    assert [(step.call, step.ok) for step in outcome.steps] == [
        ("goto", True), ("check", True), ("click", False),
    ]  # fmt: skip


def test_a_call_with_wrong_arguments_is_the_skills_failure():
    code = 'def run():\n    click(label="Save")\n    check(text="x")\n'

    outcome, _ = run(code)

    assert not outcome.ok
    assert "click(label='Save') was called wrongly" in outcome.error


def test_only_plain_data_can_be_returned():
    code = "def run():\n    return_value(read)\n"

    outcome, _ = run(code)

    assert not outcome.ok
    assert "return_value takes plain data" in outcome.error


def test_code_that_breaks_while_running_is_reported_with_its_line():
    code = 'def run(n):\n    check(text="Orders")\n    return_value(int(n) + 1)\n'

    outcome, _ = run(code, n="seven")

    assert not outcome.ok
    assert outcome.error.startswith("line 3: ValueError")


def test_a_skill_without_code_cannot_be_run():
    meta, body = parse_skill_md(FRONT.replace("params:\n{params}\n", "").format(name="guide"))

    with pytest.raises(ValueError, match="has no code to run"):
        run_skill_code(Skill(meta, body), {}, site(), BASE, ["http://site.test"])


def test_site_paths_drop_the_sites_own_address():
    assert site_path(ORDER, BASE) == "/sales/order/view/order_id/299/"
    assert site_path(BASE, BASE) == "/"
    assert site_path(f"{BASE}/", BASE) == "/"
    assert site_path("http://site.test/adminx/", BASE) == "http://site.test/adminx/"
    assert site_path("http://elsewhere.test/admin/sales/", BASE) == (
        "http://elsewhere.test/admin/sales/"
    )
