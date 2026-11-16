"""The tools the model can call, with strict schemas.

A tool call returns a short result: what was done, what changed and any error. It
never returns the page. The page is read once per step with `ToolExecutor.view()`
and shown only at the end of the prompt, so the history stays small and stable.

`run_skill` from DESIGN.md section 1 needs the memory components and is added with
them.
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

# A result line is kept in the history for the rest of the task, so it stays short.
MAX_SUMMARY_CHARS = 500

_PAGE_STATE_JS = (
    "JSON.stringify({url: location.href, title: document.title, doc: performance.timeOrigin})"
)


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
    section: int | None


class WriteNoteArgs(_Args):
    text: str


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
        "Read the page again without acting. With section set to an element's ref, show "
        "that element and everything inside it in full, including items the page text "
        "left out. With section null, wait for the page and read all of it again.",
        _schema(
            {
                "section": {
                    "type": ["integer", "null"],
                    "description": "Ref of the element to show in full, or null.",
                }
            }
        ),
        ReadPageArgs,
    ),
    ToolSpec(
        "write_note",
        "Replace your working note. Only the current page is shown to you; earlier "
        "pages are gone. Keep here what you will need later: facts and values you "
        "found, what is done, what is next.",
        _schema({"text": {"type": "string", "description": "The whole note, replacing the old."}}),
        WriteNoteArgs,
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
    # Status, what changed and the error if any. This is what the history keeps.
    summary: str
    finish: FinishArgs | None = None
    # write_note: the new working note.
    note: str | None = None
    # The document was replaced, so refs from the page before no longer exist.
    navigated: bool = False
    # read_page(section): text to show once, with the next page view.
    detail: str | None = None
    # The call acted on the page (as opposed to reading, noting or finishing).
    acted: bool = False


@dataclass(frozen=True)
class PageView:
    """The current page as the model is shown it."""

    text: str
    fingerprint: str
    url: str
    title: str


# Renders an observation, given the previous one of the same task (None at the start).
ObservationRenderer = Callable[[Observation, Observation | None], str]
# Renders the part of an observation under one ref, or None if the ref is not there.
SectionRenderer = Callable[[Observation, int], str | None]

MAX_OBSERVATION_CHARS = 300_000


def full_page(observation: Observation, previous: Observation | None) -> str:
    """The plain view: header and the complete outline."""
    return observation.render(MAX_OBSERVATION_CHARS)


def _shorten(text: str) -> str:
    if len(text) <= MAX_SUMMARY_CHARS:
        return text
    return f"{text[:MAX_SUMMARY_CHARS]}… [{len(text) - MAX_SUMMARY_CHARS} more characters]"


class ToolExecutor:
    """Validate tool calls and run them against a browser.

    render and render_section are the plug points for observation components
    (pruning, truncation, diff); the defaults show the complete page.
    """

    def __init__(
        self,
        browser: Browser,
        allowed_origins: Sequence[str],
        render: ObservationRenderer = full_page,
        render_section: SectionRenderer | None = None,
    ) -> None:
        self._browser = browser
        self._allowed_origins = frozenset(origin.lower() for origin in allowed_origins)
        self._render = render
        self._render_section = render_section
        self._specs = {spec.name: spec for spec in TOOLS}
        self._previous: Observation | None = None
        self._show_whole_page = False

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
            return ToolOutcome(False, _shorten(f"Invalid arguments for {name}: {problems}"))
        if isinstance(args, FinishArgs):
            return ToolOutcome(True, "Task finished.", finish=args)
        if isinstance(args, WriteNoteArgs):
            return ToolOutcome(True, "Note saved.", note=args.text)
        try:
            if isinstance(args, ReadPageArgs):
                return self._read(args)
            return self._act(args)
        except (ActionError, BrowserError) as exc:
            return ToolOutcome(False, _shorten(f"{name} failed: {exc}"), acted=True)

    def view(self) -> PageView:
        """Read the page as it is now. Called once per step, after the step's calls."""
        observation = observe(self._browser)
        # After read_page the model asked for the whole page, so it gets no diff.
        previous = None if self._show_whole_page else self._previous
        text = self._render(observation, previous)
        self._previous = observation
        self._show_whole_page = False
        return PageView(text, observation.fingerprint(), observation.url, observation.title)

    def recover(self, url: str) -> ToolOutcome:
        """Return to a page that worked before, after repeated failures."""
        try:
            actions.goto(self._browser, url)
        except (ActionError, BrowserError) as exc:
            return ToolOutcome(False, _shorten(f"Could not return to {url}: {exc}"))
        return ToolOutcome(True, f"Returned to the last page that worked: {url}", navigated=True)

    # -- internals ---------------------------------------------------------

    def _act(self, args: _Args) -> ToolOutcome:
        before = self._page_state()
        if isinstance(args, ClickArgs):
            message = actions.click(self._browser, args.ref)
        elif isinstance(args, TypeArgs):
            message = actions.type_text(self._browser, args.ref, args.text, args.submit)
        elif isinstance(args, GotoArgs):
            if origin_of(args.url) not in self._allowed_origins:
                allowed = ", ".join(sorted(self._allowed_origins))
                raise ActionError(f"{args.url} is outside the task's site; allowed: {allowed}")
            message = actions.goto(self._browser, args.url)
        elif isinstance(args, ScrollArgs):
            message = actions.scroll(self._browser, args.direction)
        else:  # pragma: no cover - every tool is handled above
            raise ActionError(f"no handler for {type(args).__name__}")
        after = self._page_state()
        navigated = after["doc"] != before["doc"]
        changes = list(after["dialogs"])
        if navigated or after["url"] != before["url"]:
            changes.append(f"Now on: {after['title']} ({after['url']})")
        return ToolOutcome(
            True, _shorten(" ".join([message, *changes])), navigated=navigated, acted=True
        )

    def _read(self, args: ReadPageArgs) -> ToolOutcome:
        if args.section is None:
            self._browser.settle()
            self._show_whole_page = True
            return ToolOutcome(True, "Read the page again.")
        if self._render_section is None:
            return ToolOutcome(True, "The page text already shows every element in full.")
        section = self._render_section(observe(self._browser), args.section)
        if section is None:
            raise ActionError(
                f"ref {args.section} is not on the current page; use a ref from the page text"
            )
        return ToolOutcome(
            True,
            f"Showed element [{args.section}] in full ({len(section)} characters).",
            detail=section,
        )

    def _page_state(self) -> dict[str, Any]:
        """URL, title and document identity, closing any native dialog first."""
        dialogs: list[str] = []
        dialog = self._browser.pending_dialog()
        if dialog is not None:
            # A native dialog freezes the page's scripts until it is answered.
            self._browser.cdp("Page.handleJavaScriptDialog", accept=True)
            dialogs.append(
                f"Dialog accepted: {dialog.get('type', 'dialog')}: {dialog.get('message', '')}"
            )
        evaluated = self._browser.cdp(
            "Runtime.evaluate", expression=_PAGE_STATE_JS, returnByValue=True
        )
        state = json.loads(evaluated.get("result", {}).get("value") or "{}")
        return {
            "url": state.get("url", ""),
            "title": state.get("title", ""),
            "doc": state.get("doc"),
            "dialogs": dialogs,
        }
