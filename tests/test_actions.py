"""Action primitives against a fake browser."""

from __future__ import annotations

import pytest

from browser_agent.browser import actions
from browser_agent.browser.actions import ActionError

from fakes import FakeBrowser


def test_click_hits_the_middle_of_the_element():
    browser = FakeBrowser()
    browser.element(7)
    browser.quads[7] = [[100, 200, 300, 200, 300, 240, 100, 240]]

    message = actions.click(browser, 7)

    assert message == "Clicked [7]."
    assert browser.clicks == [(200.0, 220.0)]
    assert ("DOM.scrollIntoViewIfNeeded", {"backendNodeId": 7}) in browser.cdp_calls
    assert browser.settled == 1


def test_click_on_an_option_selects_it_instead_of_using_the_mouse():
    browser = FakeBrowser()
    browser.element(8, tag="option")

    message = actions.click(browser, 8)

    assert message == "Selected option [8]."
    assert browser.clicks == []
    assert any("dispatchEvent(new Event('change'" in script for script in browser.scripts)


def test_click_on_an_element_without_a_box_falls_back_to_script():
    browser = FakeBrowser()
    browser.element(9, tag="input")
    browser.quads[9] = []

    message = actions.click(browser, 9)

    assert "by script" in message
    assert browser.clicks == []
    assert any("el.click()" in script for script in browser.scripts)


def test_a_ref_that_left_the_page_is_explained():
    with pytest.raises(ActionError, match="ref 5 is not on the current page"):
        actions.click(FakeBrowser(), 5)


def test_disabled_elements_are_not_clicked():
    browser = FakeBrowser()
    browser.element(4, disabled=True)

    with pytest.raises(ActionError, match="disabled"):
        actions.click(browser, 4)

    assert browser.clicks == []


def test_type_reports_a_field_that_did_not_take_the_text_as_typed():
    browser = FakeBrowser()
    browser.element(3, tag="input")
    browser.masks[3] = "12.00"

    assert actions.type_text(browser, 3, "12") == "Typed '12' into [3]. The field reads '12.00'."


def test_type_replaces_the_content_and_can_submit():
    browser = FakeBrowser()
    browser.element(3, tag="input")

    message = actions.type_text(browser, 3, "Hoodie", submit=True)

    assert message == "Typed 'Hoodie' into [3] and pressed Enter."
    assert browser.typed == ["Hoodie"]
    assert browser.keys == ["Enter"]
    # The old content is selected first, so the new text replaces it.
    assert any("el.select()" in script for script in browser.scripts)


def test_typing_nothing_clears_the_field():
    browser = FakeBrowser()
    browser.element(3, tag="textarea")

    actions.type_text(browser, 3, "")

    assert browser.typed == []
    assert browser.keys == ["Backspace"]


def test_type_on_a_select_chooses_by_label():
    browser = FakeBrowser()
    browser.element(6, tag="select")
    browser.options[6] = ["Pending", "Complete", "Canceled"]

    message = actions.type_text(browser, 6, "complete")

    assert message == "Chose 'Complete' in select [6]."
    assert browser.typed == []


def test_type_on_a_select_lists_the_options_when_none_matches():
    browser = FakeBrowser()
    browser.element(6, tag="select")
    browser.options[6] = ["Pending", "Complete"]

    with pytest.raises(ActionError) as caught:
        actions.type_text(browser, 6, "Shipped")

    assert "no option matching 'Shipped'" in str(caught.value)
    assert '["Pending", "Complete"]' in str(caught.value)


def test_type_on_something_that_is_not_a_field():
    browser = FakeBrowser()
    browser.element(2, tag="div")

    with pytest.raises(ActionError, match="is a <div>, not a text field or select"):
        actions.type_text(browser, 2, "x")


def test_goto_reports_a_failed_navigation():
    browser = FakeBrowser()
    browser.navigate_error = "net::ERR_NAME_NOT_RESOLVED"

    with pytest.raises(ActionError, match="ERR_NAME_NOT_RESOLVED"):
        actions.goto(browser, "http://elsewhere.test/")


def test_goto():
    browser = FakeBrowser()

    assert (
        actions.goto(browser, "http://site.test/admin/sales/")
        == "Opened http://site.test/admin/sales/."
    )
    assert browser.url == "http://site.test/admin/sales/"
    assert browser.settled == 1


@pytest.mark.parametrize(("direction", "dy"), [("down", 720.0), ("up", -720.0)])
def test_scroll_moves_most_of_a_screen(direction, dy):
    browser = FakeBrowser()

    actions.scroll(browser, direction)

    assert browser.wheels == [dy]
