"""The parts of the browser session that can be checked without a browser."""

from __future__ import annotations

from pathlib import Path

import pytest

from browser_agent.browser import session as session_module
from browser_agent.browser.session import BrowserConfig, BrowserSession, launch_args, origin_of


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

    browser.settle(timeout=30.0)

    assert browser._helpers.calls.count("count") == 0


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
