"""The skill folder: SKILL.md with its frontmatter, and the optional skill.py."""

from __future__ import annotations

import pytest

from browser_agent.memory.locators import Locator, PageIndex
from browser_agent.memory.skill import (
    Check,
    Skill,
    SkillFormatError,
    load_skill,
    parse_skill_md,
    render_skill_md,
    write_skill,
)

from fakes import load_fixture

SKILL_MD = """---
name: add-order-comment
description: Add a comment to an order and optionally notify the customer.
version: 1
params:
  order_number: {type: string, description: "The order number as the grid shows it"}
  comment: {type: string, description: The text of the comment}
  notify: {type: boolean}
url_pattern: "^/sales/order/"
required_elements:
  - {role: link, name: View, row: "{order_number}"}
preconditions:
  - {text: "Orders", why: The order grid is open}
  - {url: "^/sales/order/?$"}
time_limit_s: 90
---

Adds a comment on the order's page.

1. In the order grid, click "View" in the row of the order. Check: the page heading
   shows the order number.
2. Type the comment into "Comment". If the customer is to be notified, tick "Notify
   Customer by Email".
3. Click "Submit Comment". Check: the comment appears under "Notes for this Order".

Pitfall: the grid may be filtered; if the order is not listed, clear the filters first.
"""

CODE = """def run(order_number, comment, notify):
    click(role="link", name="View", row=order_number)
    check(text="Order # " + order_number)
    type(role="textbox", name="Comment", text=comment)
    if notify:
        click(role="checkbox", name="Notify Customer by Email")
        check(role="checkbox", name="Notify Customer by Email")
    click(role="button", name="Submit Comment")
    check(text=comment)
"""


def test_skill_md_is_split_into_checked_frontmatter_and_steps():
    meta, body = parse_skill_md(SKILL_MD)

    assert (meta.name, meta.version, meta.time_limit_s) == ("add-order-comment", 1, 90)
    assert list(meta.params) == ["order_number", "comment", "notify"]
    assert meta.params["notify"].type == "boolean"
    assert meta.required_elements == [Locator(role="link", name="View", row="{order_number}")]
    assert [check.describe() for check in meta.preconditions] == [
        'the page shows "Orders"',
        "the address matches ^/sales/order/?$",
    ]
    assert body.startswith("Adds a comment on the order's page.")
    assert "3. Click" in body


def test_rendering_and_parsing_round_trip():
    meta, body = parse_skill_md(SKILL_MD)

    assert parse_skill_md(render_skill_md(meta, body)) == (meta, body)


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (
            ("---\nname: add-order-comment", "name: add-order-comment"),
            "must start with a frontmatter",
        ),
        (("name: add-order-comment", "name: Add Order Comment"), "name"),
        (("version: 1", "version: 0"), "version"),
        (("version: 1\n", ""), "version"),
        (('url_pattern: "^/sales/order/"', 'url_pattern: "^/sales/(order"'), "regular expression"),
        (("notify: {type: boolean}", "notify: {type: checkbox}"), "params.notify.type"),
        (("notify: {type: boolean}", "_notify: {type: boolean}"), "plain identifier"),
        (("time_limit_s: 90", "time_limit_s: 3600"), "time_limit_s"),
        (("time_limit_s: 90", "time_limit_s: 90\nauthor: me"), "author"),
        (("{role: link, name: View, row", "{role: link, ref: 12, row"), "required_elements"),
        (('- {url: "^/sales/order/?$"}', '- {url: "^/x", text: "y"}'), "one of: text, url"),
        (('- {url: "^/sales/order/?$"}', "- {role: link}"), "both role and name"),
        (("description: Add a comment", "description: |\n  Two\n  lines of"), "one line"),
    ],
)
def test_a_frontmatter_that_is_not_in_form_is_refused_with_the_field_named(change, problem):
    old, new = change
    assert old in SKILL_MD

    with pytest.raises(SkillFormatError, match=problem):
        parse_skill_md(SKILL_MD.replace(old, new))


def test_a_body_without_numbered_steps_is_refused():
    front = SKILL_MD.split("---\n\n")[0] + "---\n\n"

    with pytest.raises(SkillFormatError, match="numbered steps"):
        parse_skill_md(front + "Just do what seems right.\n")


def test_arguments_are_checked_against_the_declared_types():
    meta, _ = parse_skill_md(SKILL_MD)
    good = {"order_number": "000000299", "comment": "hi", "notify": False}

    assert meta.check_args(good) == good
    with pytest.raises(SkillFormatError) as failure:
        meta.check_args({"order_number": 299, "comment": "hi", "note": "x"})

    message = str(failure.value)
    assert "unknown argument 'note'" in message
    assert "missing argument 'notify' (boolean)" in message
    assert "argument 'order_number' must be a string" in message
    assert "Expected: order_number: string, comment: string, notify: boolean" in message


def test_true_is_not_an_integer():
    meta, _ = parse_skill_md(SKILL_MD.replace("notify: {type: boolean}", "notify: {type: integer}"))

    with pytest.raises(SkillFormatError, match="'notify' must be a integer"):
        meta.check_args({"order_number": "1", "comment": "c", "notify": True})


def test_a_skill_is_written_once_and_read_back(tmp_path):
    meta, body = parse_skill_md(SKILL_MD)
    folder = tmp_path / "skills" / "add-order-comment"

    write_skill(folder, Skill(meta, body, CODE))
    loaded = load_skill(folder)

    assert loaded == Skill(meta, body, CODE)
    assert loaded.summary() == (
        "add-order-comment: Add a comment to an order and optionally notify the customer. "
        "(on ^/sales/order/)"
    )
    # A folder is never written into again: an update is a new version elsewhere.
    with pytest.raises(SkillFormatError, match="a new version goes into a new folder"):
        write_skill(folder, Skill(meta, body, None))


def test_a_skill_without_code_is_guidance_only(tmp_path):
    meta, body = parse_skill_md(SKILL_MD)
    folder = tmp_path / "add-order-comment"

    write_skill(folder, Skill(meta, body))

    assert load_skill(folder).code is None
    assert not (folder / "skill.py").exists()


def test_code_must_pass_the_sandbox_and_take_the_declared_parameters(tmp_path):
    meta, body = parse_skill_md(SKILL_MD)

    with pytest.raises(SkillFormatError, match=r"skill\.py of add-order-comment is not allowed"):
        write_skill(tmp_path / "a", Skill(meta, body, "import os\n" + CODE))
    with pytest.raises(SkillFormatError, match=r"but SKILL\.md declares"):
        write_skill(tmp_path / "b", Skill(meta, body, CODE.replace("notify", "tell")))
    assert not (tmp_path / "a").exists()


def test_the_folder_must_carry_the_skills_name(tmp_path):
    meta, body = parse_skill_md(SKILL_MD)
    write_skill(tmp_path / "something-else", Skill(meta, body))

    with pytest.raises(SkillFormatError, match="holds a skill named add-order-comment"):
        load_skill(tmp_path / "something-else")
    with pytest.raises(SkillFormatError, match=r"has no SKILL\.md"):
        load_skill(tmp_path / "missing")


def test_url_patterns_are_searched_in_the_address_relative_to_the_site():
    meta, _ = parse_skill_md(SKILL_MD)

    assert meta.matches_url("/sales/order/")
    assert meta.matches_url("/sales/order/view/order_id/299/")
    assert not meta.matches_url("/catalog/product/")
    assert not meta.matches_url("http://elsewhere.test/sales/order/")


def test_checks_say_why_they_do_not_hold():
    page = PageIndex(load_fixture("ax_order_view.json"))
    path = "/sales/order/view/order_id/299/"

    assert Check(text="Order # 000000299").failure(page, path) is None
    assert Check(url=r"^/sales/order/view/").failure(page, path) is None
    assert Check(role="button", name="Submit Comment").failure(page, path) is None
    assert Check(text="Order # 000000300").failure(page, path) == (
        'the page does not show "Order # 000000300"'
    )
    assert Check(url="^/sales/order/?$").failure(page, path) == (
        "the address /sales/order/view/order_id/299/ does not match ^/sales/order/?$"
    )
    assert Check(role="link", name="Edit").failure(page, path) == (
        '2 elements match link "Edit", where exactly one is needed'
    )
    assert Check(role="button", name="Ship It Twice").failure(page, path) == (
        '0 elements match button "Ship It Twice", where exactly one is needed'
    )


def test_placeholders_in_checks_are_filled_and_escaped_in_patterns():
    args = {"order_id": "2.9", "number": "000000299"}

    assert Check(text="Order # {number}").filled(args).text == "Order # 000000299"
    # A value put into a pattern stands for itself: the dot must not match any character.
    assert Check(url="/order_id/{order_id}/").filled(args).url == r"/order_id/2\.9/"
    assert Check(role="link", name="View", row="{number}").filled(args).locator() == Locator(
        role="link", name="View", row="000000299"
    )
