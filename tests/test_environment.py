"""The check of the browser before a task, against a fake browser."""

from __future__ import annotations

import pytest

from browser_agent.browser.environment import EnvironmentFault, TaskStart, prepare

from fakes import FakeBrowser

ORIGIN = "http://site.test"
START = TaskStart(f"{ORIGIN}/admin", ORIGIN, {"X-Auto-Login": "admin:pw"})
DASHBOARD = f"{ORIGIN}/admin/admin/dashboard/"


def clean_browser():
    browser = FakeBrowser()
    # The admin root redirects to the dashboard, as on the real site.
    browser.redirects[START.url] = DASHBOARD
    return browser


def prepared(browser, start=START):
    reported = []
    prepare(browser, start, lambda kind, **details: reported.append((kind, details)))
    return reported


def test_a_clean_browser_is_taken_to_the_start_page_and_nothing_is_reported():
    browser = clean_browser()

    assert prepared(browser) == []
    assert browser.url == DASHBOARD
    assert browser.headers == START.headers
    # Storage is looked at before the start page loads, and the page is loaded once.
    assert browser.steps == ["storage", f"goto {START.url}"]
    assert browser.restarts == 0


def test_a_tab_left_open_by_the_task_before_is_closed_and_reported():
    """What broke baseline_test_r3: the stray tab hid the agent's tab for seven tasks."""
    browser = clean_browser()
    browser.other_tabs = [f"{ORIGIN}/admin/catalog/product/edit/id/1604/"]
    browser.visible = False

    reported = prepared(browser)

    assert reported == [
        (
            "env_repaired",
            {
                "problems": [
                    f"1 extra tab(s) open: {ORIGIN}/admin/catalog/product/edit/id/1604/",
                ]
            },
        )
    ]
    assert browser.other_tabs == []
    assert browser.visible
    assert browser.url == DASHBOARD


def test_a_hidden_tab_is_brought_to_the_front():
    browser = clean_browser()
    browser.visible = False

    reported = prepared(browser)

    assert reported == [("env_repaired", {"problems": ["the agent's tab was hidden"]})]
    assert browser.visible
    # Shown before the start page loads: a hidden page is not laid out.
    assert browser.steps.index("front") < browser.steps.index(f"goto {START.url}")


def test_site_data_left_behind_is_cleared_before_the_start_page_loads():
    browser = clean_browser()
    browser.stored = ["cookies admin", "2 keys in local storage"]

    reported = prepared(browser)

    assert reported == [
        (
            "env_repaired",
            {"problems": ["site data left from before: cookies admin; 2 keys in local storage"]},
        )
    ]
    assert browser.stored == []
    assert browser.steps == ["storage", "clear", "storage", f"goto {START.url}"]
    # Reading the storage dropped the sign-in header; it is back for the task.
    assert browser.headers == START.headers


def test_a_tab_that_did_not_get_to_the_start_url_is_sent_there_again():
    browser = clean_browser()
    browser.url = f"{ORIGIN}/admin/sales/order/"
    browser.requested = browser.url
    browser.ignored_navigations = 1

    reported = prepared(browser)

    assert reported == [
        (
            "env_repaired",
            {"problems": [f"the tab was at {ORIGIN}/admin/sales/order/, not at the start URL"]},
        )
    ]
    assert browser.navigation() == (START.url, DASHBOARD)


def test_a_start_url_that_is_not_redirected_must_be_where_the_tab_is():
    browser = clean_browser()
    product = TaskStart(f"{ORIGIN}/admin/catalog/product/edit/id/237/", ORIGIN, {})

    assert prepared(browser, product) == []
    assert browser.navigation() == (product.url, product.url)


def test_several_problems_are_reported_together():
    browser = clean_browser()
    browser.other_tabs = ["about:blank"]
    browser.visible = False
    browser.stored = ["cookies admin"]

    ((kind, details),) = prepared(browser)

    assert kind == "env_repaired"
    assert details["problems"] == [
        "1 extra tab(s) open: about:blank",
        "site data left from before: cookies admin",
    ]


@pytest.mark.parametrize(
    ("fault", "reason"),
    [
        (lambda b: setattr(b, "own", None), "the agent's tab no longer exists"),
        (
            lambda b: (setattr(b, "visible", False), setattr(b, "stays_hidden", True)),
            "stays hidden",
        ),
        (
            lambda b: (
                setattr(b, "stored", ["cookies admin"]),
                setattr(b, "clearing_works", False),
            ),
            "site data could not be cleared: cookies admin",
        ),
        (lambda b: setattr(b, "ignored_navigations", 2), "does not get to the start URL"),
    ],
    ids=["tab gone", "stays hidden", "storage not cleared", "wrong url"],
)
def test_a_repair_that_fails_restarts_the_browser_and_checks_again(fault, reason):
    browser = clean_browser()
    fault(browser)
    # A new browser comes up clean, except that clearing still has to work.
    browser_restart = browser.restart

    def restart():
        browser_restart()
        browser.clearing_works = True
        browser.redirects[START.url] = DASHBOARD

    browser.restart = restart

    reported = prepared(browser)

    assert [kind for kind, _ in reported] == ["browser_restarted"]
    assert reason in reported[0][1]["reason"]
    assert browser.restarts == 1
    assert browser.url == DASHBOARD
    assert browser.visible
    assert browser.headers == START.headers


def test_what_was_repaired_before_the_restart_is_reported_with_it():
    browser = clean_browser()
    browser.other_tabs = ["about:blank"]
    browser.visible = False
    browser.ignored_navigations = 2

    ((kind, details),) = prepared(browser)

    assert kind == "browser_restarted"
    assert details["problems"][0] == "1 extra tab(s) open: about:blank"


def test_when_the_restart_does_not_help_the_task_is_not_started():
    browser = clean_browser()
    browser.own = None
    browser.restart_repairs = False
    reported = []

    with pytest.raises(EnvironmentFault, match="also after a restart"):
        prepare(browser, START, lambda kind, **details: reported.append(kind))

    assert reported == ["browser_restarted"]
    assert browser.restarts == 1
    # The start page was never opened.
    assert not any(step.startswith("goto") for step in browser.steps)


def test_a_browser_that_cannot_be_started_again_is_a_fault_too():
    browser = clean_browser()
    browser.own = None

    def restart():
        raise OSError("chrome.exe not found")

    browser.restart = restart

    with pytest.raises(EnvironmentFault, match=r"chrome\.exe not found"):
        prepare(browser, START)


def test_tabs_that_keep_opening_are_not_repaired_forever():
    class Popups(FakeBrowser):
        def close_other_tabs(self):
            return ["http://site.test/popup"]

    browser = Popups()
    browser.restart_repairs = False

    with pytest.raises(EnvironmentFault, match="keep opening"):
        prepare(browser, START)
