"""Tool schemas and the executor, against a fake browser."""

from __future__ import annotations

import json

import pytest

from browser_agent.harness.tools import FINISH_TOOL, TOOLS, FinishArgs, ToolExecutor

from fakes import FakeBrowser, load_fixture


def executor(browser=None, **kwargs):
    return ToolExecutor(browser or FakeBrowser(), allowed_origins=["http://site.test"], **kwargs)


def test_tool_set_matches_the_design_without_memory_tools():
    names = [tool.name for tool in TOOLS]

    assert names == ["click", "type", "goto", "scroll", "read_page", "finish"]
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
        ("finish", BAD_FINISH, "task_type"),
    ],
)
def test_invalid_arguments_are_explained_to_the_model(name, arguments, problem):
    outcome = executor().execute(name, arguments)

    assert not outcome.ok
    assert outcome.content.startswith(f"Invalid arguments for {name}:")
    assert problem in outcome.content


def test_unknown_tool():
    outcome = executor().execute("hover", {"ref": 1})

    assert not outcome.ok
    assert "Unknown tool 'hover'" in outcome.content


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
    assert "retrieved_data" in outcome.content


def test_finish_without_data():
    args = FinishArgs(task_type="MUTATE", status="SUCCESS", retrieved_data=None, error_details=None)

    assert args.response()["retrieved_data"] is None


def test_an_action_returns_the_page_after_it():
    browser = FakeBrowser(load_fixture("ax_login.json"))
    browser.element(11)

    outcome = executor(browser).execute("click", {"ref": 11})

    assert outcome.ok
    assert outcome.content.startswith("Clicked [11].\n\nURL: http://site.test/admin/")
    assert 'textbox "Username *"' in outcome.content
    assert outcome.url == "http://site.test/admin/"
    assert len(outcome.fingerprint) == 16
    assert browser.clicks == [(60.0, 40.0)]


def test_read_page_does_not_act():
    browser = FakeBrowser(load_fixture("ax_login.json"))

    outcome = executor(browser).execute("read_page", {})

    assert outcome.ok
    assert outcome.content.startswith("URL: http://site.test/admin/")
    assert browser.clicks == []
    assert browser.typed == []


def test_goto_is_limited_to_the_task_site():
    browser = FakeBrowser()

    blocked = executor(browser).execute("goto", {"url": "https://example.com/"})
    allowed = executor(browser).execute("goto", {"url": "http://site.test/admin/sales/"})

    assert not blocked.ok
    assert "outside the task's site" in blocked.content
    assert allowed.ok
    assert browser.url == "http://site.test/admin/sales/"


def test_action_errors_come_back_as_outcomes():
    outcome = executor().execute("click", {"ref": 999})

    assert not outcome.ok
    assert "ref 999 is not on the current page" in outcome.content


def test_recover_returns_to_a_page():
    browser = FakeBrowser()

    outcome = executor(browser).recover("http://site.test/admin/sales/")

    assert outcome.ok
    assert "Returned to the last page that worked" in outcome.content
    assert browser.url == "http://site.test/admin/sales/"


def test_observation_renderer_is_a_plug_point():
    outcome = executor(render_observation=lambda obs: f"<{obs.title}>").execute("read_page", {})

    assert outcome.content == "<Admin>"


def test_schemas_are_json_serialisable():
    json.dumps([tool.parameters for tool in TOOLS])
