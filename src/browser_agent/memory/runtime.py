"""The two skill tools of the agent: load_skill and run_skill.

They exist only while the skills switch is on. load_skill shows a skill's steps.
run_skill asks the gate; if it passes, the skill's verified code runs, without any
model call. In every other case nothing more is executed and the model gets the
skill's steps to follow itself:

- the gate rejects (no code, wrong page, an element or precondition missing): the
  result names the failed check;
- a step of the code or its check fails: the code stops there, and the result says
  which step failed, why, and which steps had been carried out before it.

A skill never finishes the task. Whatever happens, the model looks at the page and
calls finish itself.

Every decision leaves an event: skill_loaded, gate_passed, gate_rejected,
skill_code_run, skill_step_failed and skill_guided.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from browser_agent.browser.observation import observe
from browser_agent.browser.session import Browser
from browser_agent.harness.events import Notify
from browser_agent.harness.tools import ToolOutcome, ToolSpec
from browser_agent.memory.gate import check_gate
from browser_agent.memory.skill import Skill, SkillFormatError
from browser_agent.memory.skill_api import SkillRun, run_skill_code


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class LoadSkillArgs(_Args):
    name: str


class RunSkillArgs(_Args):
    name: str
    # The skill's arguments as a JSON object in a string: strict schemas cannot
    # describe an object whose keys differ from skill to skill.
    args: str


def _schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


_NAME = {"type": "string", "description": "The skill's name, as listed."}

SKILL_TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "load_skill",
        "Show the parameters and the numbered steps of a listed skill, without acting.",
        _schema({"name": _NAME}),
        LoadSkillArgs,
    ),
    ToolSpec(
        "run_skill",
        "Run a listed skill with arguments. If the skill has verified code and the page "
        "fits, the code runs and the result says what it did and returned. Otherwise "
        "nothing runs and the result gives the skill's steps to follow yourself.",
        _schema(
            {
                "name": _NAME,
                "args": {
                    "type": "string",
                    "description": "The skill's arguments as a JSON object written as a "
                    "string, such as '{\"order_id\": \"000000123\"}'; '{}' if it has none.",
                },
            }
        ),
        RunSkillArgs,
    ),
)


def _parameters(skill: Skill) -> str:
    if not skill.meta.params:
        return "Parameters: none."
    listed = "; ".join(
        f"{name} ({param.type})" + (f": {param.description}" if param.description else "")
        for name, param in skill.meta.params.items()
    )
    return f"Parameters: {listed}."


def _steps(skill: Skill, base_url: str) -> str:
    """The skill as the model reads it: parameters, how to read its addresses, steps.

    Skills give addresses relative to the site. A model that follows the steps itself
    has to know what they are relative to: left to guess, it opened the storefront
    instead of the admin and gave up on a 404.
    """
    base = base_url.rstrip("/")
    addresses = (
        f"Addresses in the steps are relative to {base}: /sales/order/ means "
        f"{base}/sales/order/. goto accepts either form."
    )
    return f"{_parameters(skill)}\n{addresses}\n\n{skill.body}"


class SkillTools:
    """load_skill and run_skill over the skills of one memory build."""

    specs = SKILL_TOOLS

    def __init__(
        self,
        skills: Mapping[str, Skill],
        browser: Browser,
        base_url: str,
        allowed_origins: Sequence[str],
        notify: Notify | None = None,
    ) -> None:
        self._skills = dict(skills)
        self._browser = browser
        self._base = base_url
        self._allowed = list(allowed_origins)
        self._notify = notify

    def handles(self, name: str) -> bool:
        return name in ("load_skill", "run_skill")

    def execute(self, args: BaseModel) -> ToolOutcome:
        if isinstance(args, LoadSkillArgs):
            return self.load(args.name)
        assert isinstance(args, RunSkillArgs)
        return self.run(args.name, args.args)

    def load(self, name: str) -> ToolOutcome:
        skill = self._skills.get(name)
        if skill is None:
            return self._unknown(name)
        self._report("skill_loaded", skill)
        code = (
            "It has verified code: run_skill can carry it out."
            if skill.code is not None
            else "It has no verified code: follow the steps yourself."
        )
        return ToolOutcome(True, f"Skill {name}. {code}\n{_steps(skill, self._base)}")

    def run(self, name: str, raw_args: str) -> ToolOutcome:
        skill = self._skills.get(name)
        if skill is None:
            return self._unknown(name)
        try:
            args = json.loads(raw_args) if raw_args.strip() else {}
            if not isinstance(args, dict):
                raise ValueError("not an object")
            args = skill.meta.check_args(args)
        except (ValueError, SkillFormatError) as exc:
            return ToolOutcome(
                False, f"Invalid arguments for skill {name}: {exc}. {_parameters(skill)}"
            )

        gate = check_gate(skill, args, observe(self._browser), self._base)
        if not gate.passed:
            self._report("gate_rejected", skill, check=gate.check, detail=gate.detail)
            self._report("skill_guided", skill, reason=gate.check)
            return ToolOutcome(
                True,
                f"Skill {name} was not run: {gate.detail}. Nothing was executed. Follow its "
                f"steps yourself, with {json.dumps(args, ensure_ascii=False)}:\n"
                f"{_steps(skill, self._base)}",
            )
        self._report("gate_passed", skill)
        run = run_skill_code(skill, args, self._browser, self._base, self._allowed)
        self._report(
            "skill_code_run",
            skill,
            ok=run.ok,
            steps=len(run.steps),
            seconds=round(run.seconds, 2),
            returned=run.returned,
            args=args,
        )
        if run.ok:
            returned = (
                f" It returned: {json.dumps(run.value, ensure_ascii=False)}."
                if run.returned
                else ""
            )
            return ToolOutcome(
                True,
                f"Skill {name} ran: {len(run.steps)} steps, every check held.{returned} The "
                "task is not finished yet: look at the page now shown, then finish.",
                navigated=True,
                acted=True,
            )
        return self._stopped(skill, args, run)

    def _stopped(self, skill: Skill, args: dict[str, Any], run: SkillRun) -> ToolOutcome:
        """The code stopped at a step: say where, and hand the steps to the model."""
        failed = run.failed_step
        where = f"step {failed.number}, {failed.call}({failed.detail})" if failed else "its code"
        self._report(
            "skill_step_failed",
            skill,
            step=failed.number if failed else 0,
            call=failed.call if failed else "",
            error=run.error[:300],
        )
        self._report("skill_guided", skill, reason="step_failed")
        done = [step for step in run.steps if step.ok]
        carried_out = (
            "\n".join(f"  {step.number}. {step.call}({step.detail})" for step in done)
            if done
            else "  none"
        )
        return ToolOutcome(
            True,
            f"Skill {skill.name} stopped at {where}: {run.error}\n"
            f"These calls had been carried out before it:\n{carried_out}\n"
            "Nothing after that was done. Look at the page now shown and continue yourself "
            f"from there, with {json.dumps(args, ensure_ascii=False)}:\n"
            f"{_steps(skill, self._base)}",
            navigated=True,
            acted=True,
        )

    def _unknown(self, name: str) -> ToolOutcome:
        listed = ", ".join(self._skills) or "none"
        return ToolOutcome(False, f"No skill named {name!r}. Skills: {listed}.")

    def _report(self, kind: str, skill: Skill, **details: Any) -> None:
        if self._notify is not None:
            self._notify(kind, skill=skill.name, version=skill.meta.version, **details)
