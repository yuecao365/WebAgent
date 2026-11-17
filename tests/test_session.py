"""The parts of the browser session that can be checked without a browser."""

from __future__ import annotations

from pathlib import Path

import pytest

from browser_agent.browser import session as session_module
from browser_agent.browser.session import (
    BrowserConfig,
    BrowserError,
    BrowserSession,
    launch_args,
    origin_of,
)


class Helpers:
    """Stands in for browser_harness.helpers: a page that settles after a while."""

    def __init__(self, load_results, element_counts):
        self.load_results = list(load_results)
        self.element_counts = list(element_counts)
        self.calls = []

    def wait_for_load(self, timeout):
        self.calls.append("load")
        result = self.load_results.pop(0) if len(self.load_results) > 1 else self.load_results[0]
        if isinstance(result, Exception):
            raise result
        return result

    def wait_for_network_idle(self, timeout, idle_ms):
        self.calls.append("idle")
        return True

    def cdp(self, method, **params):
        self.calls.append("count")
        count = (
            self.element_counts.pop(0) if len(self.element_counts) > 1 else self.element_counts[0]
        )
        return {"result": {"value": count}}


@pytest.fixture
def browser(tmp_path, monkeypatch):
    monkeypatch.setattr(session_module.time, "sleep", lambda seconds: None)
    return BrowserSession(BrowserConfig(data_dir=tmp_path))


def test_settle_waits_until_the_page_stops_growing(browser):
    browser._helpers = Helpers([True], element_counts=[600, 1900, 2048, 2048])

    browser.settle()

    # Four looks: the page kept growing until the last two agreed.
    assert browser._helpers.calls.count("count") == 4


def test_settle_asks_again_when_the_page_does_not_answer(browser):
    """A page in the middle of a navigation: the action that led there has not failed."""
    busy = TimeoutError("Runtime.evaluate timed out after 5s waiting for the daemon")
    browser._helpers = Helpers([busy, busy, True], element_counts=[2048])

    browser.settle()

    assert browser._helpers.calls.count("load") == 4
    assert browser._helpers.calls.count("count") == 2


def test_settle_gives_up_quietly_when_the_time_is_up(browser, monkeypatch):
    ticks = iter(range(0, 1000, 10))
    monkeypatch.setattr(session_module.time, "monotonic", lambda: next(ticks))
    browser._helpers = Helpers([TimeoutError("busy")], element_counts=[1])
    reported = []
    browser.notify = lambda kind, **details: reported.append((kind, details))

    browser.settle(timeout=30.0)

    assert browser._helpers.calls.count("count") == 0
    assert reported == [("settle_timeout", {"seconds": 30.0})]


def test_a_page_that_settles_reports_nothing(browser):
    browser._helpers = Helpers([True], element_counts=[2048])
    reported = []
    browser.notify = lambda kind, **details: reported.append(kind)

    browser.settle()

    assert reported == []


def test_launch_arguments_fence_the_browser_and_keep_its_tab_awake(tmp_path):
    config = BrowserConfig(data_dir=tmp_path, allowed_hosts=("localhost", "127.0.0.1"))

    args = launch_args(config, port=9333)

    assert "--remote-debugging-port=9333" in args
    assert f"--user-data-dir={Path(tmp_path) / 'profile'}" in args
    assert "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1" in args
    assert "--disable-background-timer-throttling" in args
    assert "--headless=new" in args
    assert "--headless=new" not in launch_args(BrowserConfig(data_dir=tmp_path, headless=False), 1)
    # The daemon must attach to the browser's own foreground tab.
    assert config.name == "default"


def test_origin_of():
    assert origin_of("http://LocalHost:7780/admin/sales/") == "http://localhost:7780"


class TabHelpers:
    """Stands in for browser_harness.helpers: a browser with tabs and other targets."""

    def __init__(self, targets, own="AGENT", late=None):
        self.targets = list(targets)
        self.own = own
        # target id -> how many times it is asked before it has an address
        self.late = dict(late or {})
        self.calls = []

    def current_tab(self):
        if self.own is None:
            raise RuntimeError("not_attached")
        return {"targetId": self.own, "url": "http://site.test/admin/", "title": "Admin"}

    def cdp(self, method, **params):
        params.pop("_response_timeout", None)
        self.calls.append((method, params))
        if method == "Target.getTargets":
            return {"targetInfos": list(self.targets)}
        if method == "Target.getTargetInfo":
            target = next(t for t in self.targets if t["targetId"] == params["targetId"])
            if self.late.get(target["targetId"], 0) > 0:
                self.late[target["targetId"]] -= 1
                return {"targetInfo": {**target, "url": ""}}
            return {"targetInfo": target}
        if method == "Target.closeTarget":
            self.targets = [t for t in self.targets if t["targetId"] != params["targetId"]]
        return {}

    def methods(self):
        return [method for method, _ in self.calls]


def tab(target_id, url, kind="page"):
    return {"targetId": target_id, "type": kind, "url": url}


AGENT_TAB = tab("AGENT", "http://site.test/admin/review/")
WORKER = tab("W1", "chrome-extension://abc/background.js", kind="service_worker")


def test_tabs_other_than_the_agents_are_closed_and_the_agents_is_brought_to_front(browser):
    opened = tab("NEW", "http://site.test/admin/catalog/product/edit/id/1604/")
    browser._helpers = TabHelpers([WORKER, AGENT_TAB, opened])

    closed = browser.close_other_tabs()

    assert closed == ["http://site.test/admin/catalog/product/edit/id/1604/"]
    # Only the new tab went: not the agent's, and not the extension worker.
    assert browser._helpers.targets == [WORKER, AGENT_TAB]
    assert browser._helpers.methods()[-1] == "Page.bringToFront"


def test_a_tab_that_has_just_opened_is_given_time_to_say_where_it_leads(browser):
    opened = tab("NEW", "http://site.test/admin/sales/order/")
    browser._helpers = TabHelpers([AGENT_TAB, opened], late={"NEW": 3})

    assert browser.close_other_tabs() == ["http://site.test/admin/sales/order/"]
    assert browser._helpers.methods().count("Target.getTargetInfo") == 4


def test_a_tab_without_an_address_is_closed_once_the_wait_is_over(browser, monkeypatch):
    ticks = iter(range(0, 1000, 4))
    monkeypatch.setattr(session_module.time, "monotonic", lambda: next(ticks))
    browser._helpers = TabHelpers([AGENT_TAB, tab("NEW", "about:blank")])

    assert browser.close_other_tabs() == [""]
    assert browser._helpers.targets == [AGENT_TAB]


def test_with_only_the_agents_tab_nothing_is_closed_or_brought_to_front(browser):
    browser._helpers = TabHelpers([WORKER, AGENT_TAB])

    assert browser.close_other_tabs() == []
    assert "Target.closeTarget" not in browser._helpers.methods()
    assert "Page.bringToFront" not in browser._helpers.methods()


@pytest.mark.parametrize("own", [None, "GONE"])
def test_nothing_is_closed_when_the_agents_own_tab_cannot_be_told_apart(browser, own):
    """Closing "the others" without knowing the agent's tab could close the agent's."""
    stray = tab("NEW", "http://site.test/admin/sales/")
    browser._helpers = TabHelpers([stray], own=own)

    with pytest.raises(BrowserError, match="no longer exists"):
        browser.close_other_tabs()
    assert browser._helpers.targets == [stray]
    assert browser.own_tab() is None


def test_visibility_is_read_from_the_page(browser):
    class Page:
        def cdp(self, method, **params):
            return {"result": {"value": "hidden"}}

    browser._helpers = Page()

    assert not browser.is_visible()
