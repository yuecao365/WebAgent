"""Locators, on accessibility trees saved from the local site.

ax_orders_grid.json is the order grid (cut to 13 rows), ax_order_view.json the page of
order 000000299, ax_sales_report.json the sales report form.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from browser_agent.memory.locators import Locator, LocatorError, PageIndex, fill, normalize

from fakes import load_fixture


@pytest.fixture(scope="module")
def grid():
    return PageIndex(load_fixture("ax_orders_grid.json"))


@pytest.fixture(scope="module")
def order():
    return PageIndex(load_fixture("ax_order_view.json"))


@pytest.fixture(scope="module")
def report():
    return PageIndex(load_fixture("ax_sales_report.json"))


def loc(role, name, **where):
    return Locator(role=role, name=name, **where)


def test_an_element_is_found_by_role_and_name(order):
    assert order.ref(loc("button", "Submit Comment")) == 13908
    assert order.ref(loc("textbox", "Comment")) == 12605
    assert order.ref(loc("checkbox", "Notify Customer by Email")) == 12606


def test_names_are_compared_without_case_icons_or_the_required_mark(grid, report):
    # The menu entry is named " SALES" and the field "From *".
    assert grid.ref(loc("link", "sales")) == grid.ref(loc("link", "SALES"))
    assert report.ref(loc("textbox", "From")) == report.ref(loc("textbox", "From *")) == 17061
    assert normalize("    Sales \n Orders * ") == "sales orders"


def test_a_role_is_part_of_the_match(grid):
    with pytest.raises(LocatorError, match='named "View" exists with role cell, link'):
        grid.resolve(loc("button", "View"))


def test_several_matches_are_an_error_that_lists_them(grid):
    with pytest.raises(LocatorError) as failure:
        grid.resolve(loc("link", "View"))

    message = str(failure.value)
    assert message.startswith('13 elements match link "View", not one')
    assert 'one in the row "000000299' in message
    assert "and 8 more" in message
    assert "Name the row or the section" in message


def test_a_row_text_picks_the_element_of_one_row(grid):
    by_number = grid.ref(loc("link", "View", row="000000230"))
    by_customer = grid.ref(loc("link", "View", row="Ava Brown"))

    assert by_number == by_customer == 1906


def test_a_row_text_shared_by_several_rows_is_still_an_error(grid):
    with pytest.raises(LocatorError, match='6 elements match link "View" in the row showing'):
        grid.resolve(loc("link", "View", row="Complete"))


def test_a_row_can_be_located_by_its_own_text(order):
    row = order.resolve(loc("row", "", row="Grand Total"))

    assert order.text(row) == "Grand Total $219.40"
    with pytest.raises(LocatorError, match="6 elements match"):
        order.resolve(loc("row", "", row="Total"))


def test_a_section_tells_apart_elements_with_the_same_name(report):
    with pytest.raises(LocatorError) as failure:
        report.resolve(loc("option", "Yes"))

    assert 'one in the section "Empty Rows"; one in the section "Show Actual Values"' in str(
        failure.value
    )
    assert report.ref(loc("option", "Yes", section="Empty Rows")) == 17925
    assert report.ref(loc("option", "Yes", section="Show Actual Values")) != 17925


def test_no_match_says_what_is_there_instead(grid):
    with pytest.raises(LocatorError) as missing:
        grid.resolve(loc("button", "Delete Everything"))
    with pytest.raises(LocatorError) as elsewhere:
        grid.resolve(loc("link", "View", row="000009999"))

    assert "no element matches" in str(missing.value)
    assert '"Create New Order"' in str(missing.value)
    assert "exists, but not in that row or section" in str(elsewhere.value)


def test_text_of_a_field_is_its_value_and_of_other_elements_what_they_show(report, order):
    assert report.text(report.resolve(loc("combobox", "Order Status"))) == "Any"
    assert report.text(report.resolve(loc("textbox", "From"))) == ""
    assert order.text(order.resolve(loc("button", "Submit Comment"))) == "Submit Comment"


def test_a_table_is_read_as_rows_of_cells(grid):
    table = next(node for node in grid._nodes if grid.is_table(node))

    rows = grid.table(table)

    assert len(rows) == 13
    assert rows[1][1:4] == [
        "000000065",
        "Main Website Main Website Store Default Store View",
        "May 28, 2023 6:43:55 AM",
    ]
    assert rows[1][8:10] == ["Pending", "View"]


def test_a_table_inside_a_cell_does_not_add_rows_to_the_outer_table(order):
    tables = [node for node in order._nodes if order.is_table(node)]
    items = next(table for table in tables if len(order.table(table)) == 6)

    # Header and five products; each product row holds a small table of its own.
    assert order.table(items)[1][0].startswith("Argus All-Weather Tank")
    assert [["Ordered", "1"]] in [order.table(table) for table in tables]


def test_page_text_is_searched_in_names_and_values(order, report):
    assert order.has_text("Order # 000000299")
    assert order.has_text("grand total")
    assert report.has_text("Any")  # the value of a dropdown
    assert not order.has_text("000000300")
    assert not order.has_text("  ")


def test_placeholders_are_filled_from_the_arguments():
    locator = loc("link", "View", row="{order_number}")

    assert locator.filled({"order_number": "000000230"}) == loc("link", "View", row="000000230")
    assert fill("Order # {n}", {"n": 7}) == "Order # 7"
    with pytest.raises(LocatorError, match=r"no value for the placeholder \{order_number\}"):
        locator.filled({})


def test_a_locator_names_what_it_looks_for():
    assert loc("link", "View", row="000000230").describe() == (
        'link "View" in the row showing "000000230"'
    )
    assert loc("option", "Yes", section="Empty Rows").describe() == (
        'option "Yes" in the section "Empty Rows"'
    )
    with pytest.raises(ValidationError):
        Locator(role="link", name="View", ref=12)
    with pytest.raises(ValidationError):
        Locator(role=" ", name="View")
    with pytest.raises(ValidationError):
        Locator(role="link", name="View", row="")
