"""The tools the model can call, with strict schemas.

`run_skill` and `write_note` from DESIGN.md section 1 need the memory and context
components and are added with them.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from browser_agent.browser import actions
from browser_agent.browser.actions import ActionError
from browser_agent.browser.observation import Observation, observe
from browser_agent.browser.session import Browser, BrowserError, origin_of

TaskType = Literal["RETRIEVE", "MUTATE", "NAVIGATE"]
Status = Literal[
    "SUCCESS",
    "NOT_FOUND_ERROR",
    "ACTION_NOT_ALLOWED_ERROR",
    "PERMISSION_DENIED_ERROR",
    "DATA_VALIDATION_ERROR",
    "UNKNOWN_ERROR",
]


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ClickArgs(_Args):
    ref: int


class TypeArgs(_Args):
    ref: int
    text: str
    submit: bool


class GotoArgs(_Args):
    url: str


class ScrollArgs(_Args):
    direction: Literal["up", "down"]


class ReadPageArgs(_Args):
    pass


class FinishArgs(_Args):
    """The structured final answer; the fields follow the WebArena Verified response."""

    task_type: TaskType
    status: Status
    # A JSON array encoded as a string: strict schemas cannot describe a list whose
    # items may be objects with task-specific keys.
    retrieved_data: str | None
    error_details: str | None

    @field_validator("retrieved_data")
    @classmethod
    def _must_be_json_array(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"retrieved_data is not valid JSON: {exc}") from exc
        if not isinstance(parsed, list):
            raise ValueError("retrieved_data must be a JSON array, for example '[\"a\", 3]'")
        return value

    def data(self) -> list[Any] | None:
        return None if self.retrieved_data is None else json.loads(self.retrieved_data)

    def response(self) -> dict[str, Any]:
        """The answer in the shape the evaluator reads."""
        return {
            "task_type": self.task_type,
            "status": self.status,
            "retrieved_data": self.data(),
            "error_details": self.error_details,
        }


def _schema(properties: dict[str, Any]) -> dict[str, Any]:
    # Strict tool calling needs every property required and no extra properties.
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    args_model: type[_Args]


_REF = {"type": "integer", "description": "The number in [brackets] before the element."}

TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "click",
        "Click an element. Clicking an option selects it in its dropdown.",
        _schema({"ref": _REF}),
        ClickArgs,
    ),
    ToolSpec(
        "type",
        "Replace the content of a text field with text. On a select or combobox, choose "
        "the option whose label matches text. Set submit to true to press Enter afterwards.",
        _schema(
            {
                "ref": _REF,
                "text": {"type": "string", "description": "The text to enter. Empty clears."},
                "submit": {"type": "boolean", "description": "Press Enter after typing."},
            }
        ),
        TypeArgs,
    ),
    ToolSpec(
        "goto",
        "Open a URL in the current tab. Only URLs of the task's site are allowed.",
        _schema({"url": {"type": "string", "description": "An absolute URL."}}),
        GotoArgs,
    ),
    ToolSpec(
        "scroll",
        "Scroll the page by most of one screen. The page text always lists the whole "
        "page, so scrolling is only needed when content loads as you scroll.",
        _schema({"direction": {"type": "string", "enum": ["up", "down"]}}),
        ScrollArgs,
    ),
    ToolSpec(
        "read_page",
        "Read the current page again without acting, for example after waiting for it "
        "to finish loading.",
        _schema({}),
        ReadPageArgs,
    ),
    ToolSpec(
        "finish",
        "End the task with the final answer. Call it once the objective is achieved, or "
        "when it cannot be achieved.",
        _schema(
            {
                "task_type": {
                    "type": "string",
                    "enum": ["RETRIEVE", "MUTATE", "NAVIGATE"],
                    "description": "What the task mainly asked for.",
                },
                "status": {
                    "type": "string",
                    "enum": [
                        "SUCCESS",
                        "NOT_FOUND_ERROR",
                        "ACTION_NOT_ALLOWED_ERROR",
                        "PERMISSION_DENIED_ERROR",
                        "DATA_VALIDATION_ERROR",
                        "UNKNOWN_ERROR",
                    ],
                },
                "retrieved_data": {
                    "type": ["string", "null"],
                    "description": "For RETRIEVE: a JSON array written as a string, such as "
                    '\'["Jane Doe"]\', \'[42]\' or \'[{"name": "a", "price": 3.5}]\'. '
                    "Otherwise null.",
                },
                "error_details": {
                    "type": ["string", "null"],
                    "description": "Null on SUCCESS, else a short reason.",
                },
            }
        ),
        FinishArgs,
    ),
)

FINISH_TOOL = TOOLS[-1]


@dataclass(frozen=True)
class ToolOutcome:
    """What a tool call produced."""

    ok: bool
    content: str
    finish: FinishArgs | None = None
    # Set when the call read the page, so the loop can notice an unchanged page.
    fingerprint: str | None = None
    url: str | None = None


ObservationRenderer = Callable[[Observation], str]


class ToolExecutor:
    """Validate tool calls and run them against a browser.

    render_observation is the plug point for observation components (pruning, diff):
    the default shows the full observation.
    """

    def __init__(
        self,
        browser: Browser,
        allowed_origins: Sequence[str],
        render_observation: ObservationRenderer = Observation.render,
        max_observation_chars: int | None = 300_000,
    ) -> None:
        self._browser = browser
        self._allowed_origins = frozenset(origin.lower() for origin in allowed_origins)
        self._render = render_observation
        self._max_chars = max_observation_chars
        self._specs = {spec.name: spec for spec in TOOLS}

    def execute(self, name: str, arguments: Any) -> ToolOutcome:
        """Run one tool call; every failure comes back as an outcome the model can read."""
        spec = self._specs.get(name)
        if spec is None:
            return ToolOutcome(False, f"Unknown tool {name!r}. Tools: {', '.join(self._specs)}.")
        try:
            args = spec.args_model.model_validate(arguments)
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(part) for part in err['loc']) or 'arguments'}: {err['msg']}"
                for err in exc.errors()
            )
            return ToolOutcome(False, f"Invalid arguments for {name}: {problems}")
        if isinstance(args, FinishArgs):
            return ToolOutcome(True, "Task finished.", finish=args)
        try:
            message = self._act(args)
            return self._with_page(message)
        except (ActionError, BrowserError) as exc:
            return ToolOutcome(False, f"{name} failed: {exc}")

    def read_page(self) -> ToolOutcome:
        """The current page, used for the first observation of a task."""
        try:
            return self._with_page("")
        except BrowserError as exc:
            return ToolOutcome(False, f"read_page failed: {exc}")

    def recover(self, url: str) -> ToolOutcome:
        """Return to a page that worked before, after repeated failures."""
        try:
            actions.goto(self._browser, url)
            return self._with_page(f"Returned to the last page that worked: {url}")
        except (ActionError, BrowserError) as exc:
            return ToolOutcome(False, f"Could not return to {url}: {exc}")

    def _act(self, args: _Args) -> str:
        if isinstance(args, ClickArgs):
            return actions.click(self._browser, args.ref)
        if isinstance(args, TypeArgs):
            return actions.type_text(self._browser, args.ref, args.text, args.submit)
        if isinstance(args, GotoArgs):
            if origin_of(args.url) not in self._allowed_origins:
                allowed = ", ".join(sorted(self._allowed_origins))
                raise ActionError(f"{args.url} is outside the task's site; allowed: {allowed}")
            return actions.goto(self._browser, args.url)
        if isinstance(args, ScrollArgs):
            return actions.scroll(self._browser, args.direction)
        return ""  # read_page: nothing to do before reading

    def _with_page(self, message: str) -> ToolOutcome:
        observation = observe(self._browser, max_chars=self._max_chars)
        text = self._render(observation)
        content = f"{message}\n\n{text}" if message else text
        return ToolOutcome(
            True, content, fingerprint=observation.fingerprint(), url=observation.url
        )
