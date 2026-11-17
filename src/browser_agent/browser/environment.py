"""Check the browser before every task, and repair what is wrong.

What one task leaves behind must not reach the next. In baseline_test_r3 a tab opened
in one task hid the agent's tab, and the seven tasks after it could not open a menu.
So the check runs per task, not per run, and before the task's first observation:

- there is exactly one tab, and it is the agent's;
- that tab is the one shown (a hidden page is not laid out);
- the browser holds nothing for the site: no cookies, no stored data;
- the tab is at the task's start URL.

Whatever is wrong is repaired and reported as one env_repaired event that says what it
was. If a repair does not hold, the browser is restarted (browser_restarted) and the
check runs once more on the new browser. If that fails too, EnvironmentFault is raised
and the task is not run: an agent working in a broken browser would be measuring the
browser, not the agent.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from browser_agent.browser import actions
from browser_agent.browser.actions import ActionError
from browser_agent.browser.session import Browser, BrowserError, origin_of
from browser_agent.harness.events import Notify

# OSError: the browser binary could not be started again.
_FAILURES = (BrowserError, ActionError, OSError)


class EnvironmentFault(BrowserError):
    """The browser could not be put into a clean state for the task."""


class TaskBrowser(Browser, Protocol):
    """What the check needs from a browser, beyond what the actions need."""

    def own_tab(self) -> str | None: ...

    def is_visible(self) -> bool: ...

    def bring_to_front(self) -> None: ...

    def stored_site_data(self, origin: str) -> list[str]: ...

    def clear_site_data(self, origins: Sequence[str]) -> None: ...

    def set_extra_headers(self, headers: Mapping[str, str]) -> None: ...

    def navigation(self) -> tuple[str, str]: ...

    def restart(self) -> None: ...


@dataclass(frozen=True)
class TaskStart:
    """Where a task begins."""

    url: str
    # The site whose stored data must be gone before the task.
    origin: str
    # Sent with every request of the tab; the site signs the agent in by a header.
    headers: Mapping[str, str]


def prepare(browser: TaskBrowser, start: TaskStart, notify: Notify | None = None) -> None:
    """Leave the browser clean and on the task's start page, or raise EnvironmentFault."""

    def report(kind: str, **details: object) -> None:
        if notify is not None:
            notify(kind, **details)

    problems: list[str] = []
    try:
        _check_and_repair(browser, start, problems)
    except _FAILURES as first:
        report("browser_restarted", reason=str(first)[:300], problems=list(problems))
        problems = []
        try:
            browser.restart()
            _check_and_repair(browser, start, problems)
        except _FAILURES as second:
            raise EnvironmentFault(
                f"the browser could not be prepared for the task, also after a restart: "
                f"{second} (before the restart: {first})"
            ) from second
    if problems:
        report("env_repaired", problems=problems)


def _check_and_repair(browser: TaskBrowser, start: TaskStart, problems: list[str]) -> None:
    """Run the four checks in order; a problem that was repaired is added to problems.

    Storage is checked before the start page is opened, because that page stores
    things itself while it loads.
    """
    if browser.own_tab() is None:
        raise EnvironmentFault("the agent's tab no longer exists")
    closed = browser.close_other_tabs()
    if closed:
        problems.append(
            f"{len(closed)} extra tab(s) open: {', '.join(u or '(blank)' for u in closed)}"
        )
        if browser.close_other_tabs():
            raise EnvironmentFault("tabs other than the agent's keep opening")

    _show(browser, problems)

    stored = browser.stored_site_data(start.origin)
    if stored:
        problems.append(f"site data left from before: {'; '.join(stored)}")
        browser.clear_site_data([start.origin])
        still = browser.stored_site_data(start.origin)
        if still:
            raise EnvironmentFault(f"site data could not be cleared: {'; '.join(still)}")

    browser.set_extra_headers(start.headers)
    actions.goto(browser, start.url)
    if not _at_start(browser, start):
        problems.append(f"the tab was at {browser.navigation()[1]}, not at the start URL")
        actions.goto(browser, start.url)
        if not _at_start(browser, start):
            raise EnvironmentFault(
                f"the tab does not get to the start URL {start.url}: "
                f"it is at {browser.navigation()[1]}"
            )
    # Once more: loading the start page must not have hidden the tab either.
    _show(browser, problems)


def _show(browser: TaskBrowser, problems: list[str]) -> None:
    if browser.is_visible():
        return
    problems.append("the agent's tab was hidden")
    browser.bring_to_front()
    if not browser.is_visible():
        raise EnvironmentFault("the agent's tab stays hidden")


def _at_start(browser: TaskBrowser, start: TaskStart) -> bool:
    """The tab's document is the one the start URL leads to.

    The site may redirect the start URL (the admin root goes to the dashboard), so
    the address shown need not equal it. What counts is that the tab was sent to the
    start URL and ended on a page of the site.
    """
    asked, current = browser.navigation()
    return asked == start.url and origin_of(current) == start.origin
