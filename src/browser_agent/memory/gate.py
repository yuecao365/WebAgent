"""The gate in front of skill code.

Code runs only when all of this holds on the page the agent is on:

1. the skill has code (it passed verification);
2. the page's address matches the skill's url_pattern;
3. every required element resolves to exactly one element;
4. every precondition holds.

The checks are made in this order and the first that fails is the answer. When the
gate rejects, nothing has been executed: the agent is told which check failed and
follows the skill's steps itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from browser_agent.browser.observation import Observation
from browser_agent.memory.locators import LocatorError, PageIndex
from browser_agent.memory.skill import Skill
from browser_agent.memory.skill_api import site_path

NO_CODE = "no_code"
URL = "url_pattern"
ELEMENT = "required_element"
PRECONDITION = "precondition"


@dataclass(frozen=True)
class GateResult:
    passed: bool
    # Which kind of check failed: no_code, url_pattern, required_element, precondition.
    check: str = ""
    # The failed check in words, for the model and the log.
    detail: str = ""


def check_gate(
    skill: Skill, args: Mapping[str, Any], observation: Observation, base_url: str
) -> GateResult:
    """Whether the skill's code may run on this page with these arguments."""
    if skill.code is None:
        return GateResult(False, NO_CODE, "this skill has no verified code; follow its steps")
    path = site_path(observation.url, base_url)
    if not skill.meta.matches_url(path):
        return GateResult(
            False, URL, f"the page's address {path} does not match {skill.meta.url_pattern}"
        )
    index = PageIndex(observation.nodes)
    for locator in skill.meta.required_elements:
        try:
            filled = locator.filled(args)
        except LocatorError as exc:
            return GateResult(False, ELEMENT, str(exc))
        found = len(index.find(filled))
        if found != 1:
            return GateResult(
                False,
                ELEMENT,
                f"{found} elements match {filled.describe()}, where exactly one is needed",
            )
    for check in skill.meta.preconditions:
        try:
            failure = check.filled(args).failure(index, path)
        except LocatorError as exc:
            failure = str(exc)
        if failure is not None:
            return GateResult(False, PRECONDITION, failure)
    return GateResult(True)
