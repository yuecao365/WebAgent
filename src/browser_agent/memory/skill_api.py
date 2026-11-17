"""The calls skill code can make, and one run of a skill's code.

Seven calls and nothing else: goto, click, type, select, read, check, return_value.
Elements are named by locator (role and accessible name, optionally a row or a
section), resolved against the page as it is when the call is made. A call that
cannot do exactly what it says raises; a run never guesses.

No model is called here. A run either completes every step and check, or stops at
the first one that fails and says which.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from browser_agent.browser import actions
from browser_agent.browser.actions import ActionError
from browser_agent.browser.observation import Observation, observe
from browser_agent.browser.session import Browser, BrowserError, origin_of
from browser_agent.harness.sandbox import SandboxError, run_sandboxed
from browser_agent.memory.locators import Locator, LocatorError, PageIndex
from browser_agent.memory.skill import PRIMITIVES, Check, Skill

_FIELD_READS = re.compile(r" The field reads (.+)\.$")


class SkillStepError(RuntimeError):
    """A step could not be done as written, or a check after it did not hold."""


class SkillTimeout(SkillStepError):
    """The skill used up its time limit."""


def site_path(url: str, base_url: str) -> str:
    """A page's address relative to the site, as url patterns are written against.

    The site's own address differs between machines and containers; a skill must not
    carry it. An address outside the site is returned whole, so no pattern written
    for the site matches it.
    """
    base = base_url.rstrip("/")
    if url == base:
        return "/"
    return url[len(base) :] if url.startswith(base + "/") else url


@dataclass(frozen=True)
class StepRecord:
    """One call a skill made, for the event log."""

    number: int
    call: str
    detail: str
    ok: bool
    result: str = ""


@dataclass
class SkillRun:
    """What one run of a skill's code did."""

    ok: bool
    steps: list[StepRecord] = field(default_factory=list)
    # What the code handed back with return_value, if anything.
    value: Any = None
    returned: bool = False
    # The step that failed and why; empty when every step and check held.
    error: str = ""
    failed_step: StepRecord | None = None
    seconds: float = 0.0


class SkillRuntime:
    """Binds the seven calls to a browser for the length of one run."""

    def __init__(
        self,
        browser: Browser,
        base_url: str,
        allowed_origins: Sequence[str],
        time_limit_s: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._browser = browser
        self._base = base_url.rstrip("/")
        self._allowed = frozenset(origin.lower() for origin in allowed_origins)
        self._clock = clock
        self._started = clock()
        self._deadline = self._started + time_limit_s
        self._limit = time_limit_s
        self.steps: list[StepRecord] = []
        self.value: Any = None
        self.returned = False

    def primitives(self) -> dict[str, Callable[..., Any]]:
        return {name: self._logged(name, getattr(self, f"_{name}")) for name in PRIMITIVES}

    def elapsed(self) -> float:
        return self._clock() - self._started

    # -- the calls ---------------------------------------------------------

    def _goto(self, path: str) -> str:
        if not isinstance(path, str) or not path.startswith("/"):
            raise SkillStepError("goto takes an address relative to the site, starting with /")
        url = self._base + path
        if origin_of(url) not in self._allowed:
            raise SkillStepError(f"{url} is outside the task's site")
        actions.goto(self._browser, url)
        return self._after_change(f"Opened {path}.")

    def _click(
        self, role: str, name: str, row: str | None = None, section: str | None = None
    ) -> str:
        ref = self._ref(role, name, row, section)
        return self._after_change(actions.click(self._browser, ref))

    def _type(
        self,
        role: str,
        name: str,
        text: str,
        row: str | None = None,
        section: str | None = None,
        submit: bool = False,
    ) -> str:
        ref = self._ref(role, name, row, section)
        message = actions.type_text(self._browser, ref, str(text), bool(submit))
        differs = _FIELD_READS.search(message)
        if differs is not None:
            # An input mask or a length limit changed what was typed; the step did
            # not do what the skill says it does.
            raise SkillStepError(f"typed {text!r}, but the field reads {differs.group(1)}")
        return self._after_change(message) if submit else message

    def _select(
        self,
        role: str,
        name: str,
        option: str,
        row: str | None = None,
        section: str | None = None,
    ) -> str:
        ref = self._ref(role, name, row, section)
        return self._after_change(actions.type_text(self._browser, ref, str(option), False))

    def _read(
        self, role: str, name: str, row: str | None = None, section: str | None = None
    ) -> str | list[list[str]]:
        index = self._index()
        node = index.resolve(Locator(role=role, name=name, row=row, section=section))
        return index.table(node) if index.is_table(node) else index.text(node)

    def _check(
        self,
        text: str | None = None,
        url: str | None = None,
        role: str | None = None,
        name: str | None = None,
        row: str | None = None,
        section: str | None = None,
    ) -> str:
        wanted = Check(text=text, url=url, role=role, name=name, row=row, section=section)
        observation = self._observe()
        failure = wanted.failure(
            PageIndex(observation.nodes), site_path(observation.url, self._base)
        )
        if failure is not None:
            raise SkillStepError(f"check failed: {failure}")
        return f"Holds: {wanted.describe()}."

    def _return_value(self, value: Any) -> str:
        try:
            json.dumps(value)
        except (TypeError, ValueError) as exc:
            raise SkillStepError(f"return_value takes plain data: {exc}") from exc
        self.value, self.returned = value, True
        return "Value recorded."

    # -- internals ---------------------------------------------------------

    def _logged(self, name: str, call: Callable[..., Any]) -> Callable[..., Any]:
        """Wrap a call: look at the clock first, record what happened after."""

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            detail = ", ".join(
                [*(repr(arg) for arg in args), *(f"{k}={v!r}" for k, v in kwargs.items())]
            )
            number = len(self.steps) + 1
            if self._clock() >= self._deadline:
                error = f"the skill passed its time limit of {self._limit:g} seconds"
                self.steps.append(StepRecord(number, name, detail, False, error))
                raise SkillTimeout(error)
            try:
                result = call(*args, **kwargs)
            except (SkillStepError, LocatorError, ActionError, BrowserError) as exc:
                self.steps.append(StepRecord(number, name, detail, False, str(exc)[:300]))
                raise
            except (TypeError, ValueError) as exc:
                # Wrong arguments to a call are the skill's mistake, not a harness error.
                self.steps.append(StepRecord(number, name, detail, False, str(exc)[:300]))
                raise SkillStepError(f"{name}({detail}) was called wrongly: {exc}") from exc
            shown = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            self.steps.append(StepRecord(number, name, detail, True, shown[:300]))
            # Only read hands something back; the other calls act or raise.
            return result if name == "read" else None

        return wrapped

    def _observe(self) -> Observation:
        return observe(self._browser)

    def _index(self) -> PageIndex:
        return PageIndex(self._observe().nodes)

    def _ref(self, role: str, name: str, row: str | None, section: str | None) -> int:
        return self._index().ref(Locator(role=role, name=name, row=row, section=section))

    def _after_change(self, message: str) -> str:
        """A skill works in one tab; a step that opens another did not do its job."""
        opened = self._browser.close_other_tabs()
        if opened:
            raise SkillStepError(
                f"the step opened a new tab at {opened[0] or 'an unknown address'}; it was closed"
            )
        return message


def run_skill_code(
    skill: Skill,
    args: dict[str, Any],
    browser: Browser,
    base_url: str,
    allowed_origins: Sequence[str],
    clock: Callable[[], float] = time.monotonic,
) -> SkillRun:
    """Run a skill's code once. Never raises for what the skill did; the run says it."""
    if skill.code is None:
        raise ValueError(f"skill {skill.name} has no code to run")
    runtime = SkillRuntime(browser, base_url, allowed_origins, skill.meta.time_limit_s, clock)
    error = ""
    try:
        run_sandboxed(skill.code, runtime.primitives(), args)
    except (SkillStepError, LocatorError, ActionError, BrowserError, SandboxError) as exc:
        error = str(exc)
    failed = next((step for step in runtime.steps if not step.ok), None)
    return SkillRun(
        ok=not error,
        steps=runtime.steps,
        value=runtime.value,
        returned=runtime.returned,
        error=error,
        failed_step=failed,
        seconds=runtime.elapsed(),
    )
