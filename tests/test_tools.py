"""Tool schemas and the executor, against a fake browser."""

from __future__ import annotations

import json

import pytest

from browser_agent.harness.tools import (
    FINISH_TOOL,
    MAX_SUMMARY_CHARS,
    TOOLS,
    FinishArgs,
    ToolExecutor,
)

from fakes import FakeBrowser, load_fixture


def executor(browser=None, **kwargs):
    return ToolExecutor(browser or FakeBrowser(), allowed_origins=["http://site.test"], **kwargs)


def test_tool_set():
    names = [tool.name for tool in TOOLS]

    assert names == ["click", "type", "goto", "scroll", "read_page", "write_note", "finish"]
    assert FINISH_TOOL.name == "finish"


@pytest.mark.parametrize("tool", TOOLS, ids=lambda tool: tool.name)
def test_schemas_are_strict(tool):
    schema = tool.parameters

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == list(schema["properties"])
    # The schema the model sees and the model that validates must agree on the fields.
    assert set(schema["properties"]) == set(tool.args_model.model_fields)


BAD_FINISH = {
    "task_type": "ANSWER",
    "status": "SUCCESS",
    "retrieved_data": None,
    "error_details": None,
}


@pytest.mark.parametrize(
    ("name", "arguments", "problem"),
    [
        ("click", {}, "ref"),
        ("click", {"ref": "12"}, "ref"),
        ("click", {"ref": 12, "button": "left"}, "button"),
        ("type", {"ref": 3, "text": "x"}, "submit"),
        ("scroll", {"direction": "left"}, "direction"),
        ("read_page", {}, "section"),
        ("write_note", {"text": 5}, "text"),
        ("finish", BAD_FINISH, "task_type"),
    ],
)
def test_invalid_arguments_are_explained_to_the_model(name, arguments, problem):
    outcome = executor().execute(name, arguments)

    assert not outcome.ok
    assert outcome.summary.startswith(f"Invalid arguments for {name}:")
    assert problem in outcome.summary


def test_unknown_tool():
    outcome = executor().execute("hover", {"ref": 1})

    assert not outcome.ok
    assert "Unknown tool 'hover'" in outcome.summary


def test_finish_parses_the_json_answer():
    outcome = executor().execute(
        "finish",
        {
            "task_type": "RETRIEVE",
            "status": "SUCCESS",
            "retrieved_data": '[{"name": "Ann", "total": 12.5}]',
            "error_details": None,
        },
    )

    assert outcome.finish.response() == {
        "task_type": "RETRIEVE",
        "status": "SUCCESS",
        "retrieved_data": [{"name": "Ann", "total": 12.5}],
        "error_details": None,
    }


@pytest.mark.parametrize("data", ["Ann", '{"name": "Ann"}', "[1, 2"])
def test_finish_rejects_data_that_is_not_a_json_array(data):
    outcome = executor().execute(
        "finish",
        {
            "task_type": "RETRIEVE",
            "status": "SUCCESS",
            "retrieved_data": data,
            "error_details": None,
        },
    )

    assert not outcome.ok
    assert outcome.finish is None
    assert "retrieved_data" in outcome.summary


def test_finish_without_data():
    args = FinishArgs(task_type="MUTATE", status="SUCCESS", retrieved_data=None, error_details=None)

    assert args.response()["retrieved_data"] is None


def test_an_action_returns_a_short_result_not_the_page():
    browser = FakeBrowser(load_fixture("ax_login.json"))
    browser.element(11)

    outcome = executor(browser).execute("click", {"ref": 11})

    assert outcome.ok
    assert outcome.acted
    assert outcome.summary == "Clicked [11]."
    assert not outcome.navigated
    assert browser.clicks == [(60.0, 40.0)]


def test_a_click_that_loads_a_page_says_where_it_led():
    browser = FakeBrowser()
    browser.element(11, tag="a")
    browser.links[11] = "http://site.test/admin/sales/order/"

    outcome = executor(browser).execute("click", {"ref": 11})

    assert outcome.navigated
    assert (
        outcome.summary == "Clicked [11]. Now on: Next page (http://site.test/admin/sales/order/)"
    )


def test_goto_reports_the_new_page_and_is_limited_to_the_task_site():
    browser = FakeBrowser()

    blocked = executor(browser).execute("goto", {"url": "https://example.com/"})
    allowed = executor(browser).execute("goto", {"url": "http://site.test/admin/sales/"})

    assert not blocked.ok
    assert "outside the task's site" in blocked.summary
    assert allowed.ok
    assert allowed.navigated
    assert allowed.summary.endswith("Now on: Admin (http://site.test/admin/sales/)")
    assert browser.url == "http://site.test/admin/sales/"


def test_a_dialog_that_opens_is_accepted_and_reported():
    browser = FakeBrowser()
    browser.element(11)
    real_click = browser.click_at

    def click_and_open_dialog(x, y):
        real_click(x, y)
        browser.dialog = {"type": "confirm", "message": "Delete this review?"}

    browser.click_at = click_and_open_dialog

    outcome = executor(browser).execute("click", {"ref": 11})

    assert outcome.summary == "Clicked [11]. Dialog accepted: confirm: Delete this review?"
    assert ("Page.handleJavaScriptDialog", {"accept": True}) in browser.cdp_calls


def test_action_errors_come_back_as_outcomes():
    outcome = executor().execute("click", {"ref": 999})

    assert not outcome.ok
    assert "ref 999 is not on the current page" in outcome.summary


def test_long_results_are_cut_and_say_so():
    browser = FakeBrowser()
    browser.element(6, tag="select")
    browser.options[6] = [f"Option number {n}" for n in range(60)]

    outcome = executor(browser).execute("type", {"ref": 6, "text": "nothing", "submit": False})

    assert not outcome.ok
    assert len(outcome.summary) < MAX_SUMMARY_CHARS + 60
    assert outcome.summary.endswith("more characters]")


def test_view_reads_the_page():
    browser = FakeBrowser(load_fixture("ax_login.json"))

    page = executor(browser).view()

    assert page.text.startswith("URL: http://site.test/admin/\nTitle: Admin")
    assert 'textbox "Username *"' in page.text
    assert page.url == "http://site.test/admin/"
    assert page.title == "Admin"
    assert len(page.fingerprint) == 16


def test_the_renderer_is_a_plug_point_and_gets_the_previous_page():
    seen = []

    def render(observation, previous):
        seen.append(previous)
        return f"<{observation.title}>"

    tools = executor(render=render)

    assert tools.view().text == "<Admin>"
    tools.view()
    assert seen[0] is None
    assert seen[1].title == "Admin"


def test_read_page_without_a_section_waits_and_reads_again():
    browser = FakeBrowser()

    outcome = executor(browser).execute("read_page", {"section": None, "find": None})

    assert outcome.ok
    assert not outcome.acted
    assert outcome.summary == "Read the page again."
    assert browser.settled == 1


def test_after_read_page_the_next_view_is_the_whole_page_not_a_diff():
    previous_pages = []
    tools = executor(render=lambda observation, previous: previous_pages.append(previous) or "x")

    tools.view()
    tools.view()
    tools.execute("read_page", {"section": None, "find": None})
    tools.view()
    tools.view()

    # The renderer diffs against the previous page; None makes it show everything.
    assert [page is None for page in previous_pages] == [True, False, True, False]


def test_read_page_section_returns_the_detail_separately():
    def render_section(observation, ref):
        return "row A\nrow B" if ref == 7 else None

    tools = executor(render_section=render_section)

    found = tools.execute("read_page", {"section": 7, "find": None})
    missing = tools.execute("read_page", {"section": 8, "find": None})

    assert found.detail == "row A\nrow B"
    assert found.summary == "Showed element [7] in full (11 characters)."
    assert not missing.ok
    assert "ref 8 is not on the current page" in missing.summary


def test_read_page_find_searches_the_page_and_returns_the_matches():
    asked = []

    def search(observation, text, ref):
        asked.append((text, ref))
        return f"1 lines contain {text!r}:\n[30] row: 000000302 | Pending"

    tools = executor(search=search)

    whole_page = tools.execute("read_page", {"section": None, "find": "302"})
    in_section = tools.execute("read_page", {"section": 104, "find": "302"})

    assert asked == [("302", None), ("302", 104)]
    assert whole_page.ok
    assert not whole_page.acted
    # The history keeps the count; the matching lines are shown once, with the next page.
    assert whole_page.summary == "1 lines contain '302':"
    assert whole_page.detail.endswith("[30] row: 000000302 | Pending")
    assert in_section.ok


def test_write_note_returns_the_note():
    outcome = executor().execute("write_note", {"text": "total: 30.50"})

    assert outcome.ok
    assert outcome.note == "total: 30.50"
    assert outcome.summary == "Note saved."


def test_recover_returns_to_a_page():
    browser = FakeBrowser()

    outcome = executor(browser).recover("http://site.test/admin/sales/")

    assert outcome.ok
    assert "Returned to the last page that worked" in outcome.summary
    assert browser.url == "http://site.test/admin/sales/"


def test_schemas_are_json_serialisable():
    json.dumps([tool.parameters for tool in TOOLS])
