"""The agent loop: one model call per step, under budgets.

The prompt is laid out so that a provider's prompt cache can reuse it from step to
step: system prompt, tool schemas, task, then a history that is only ever appended
to, and last a tail that is rebuilt every step. The history holds each call with a
one-line result. The page, the working note and the step count live in the tail
alone, so nothing that changes sits in front of something that does not.

The loop knows nothing about browsers or providers. It talks to a ToolExecutor and
an LLMClient, which is what lets the tests drive it with scripted replies.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field

from browser_agent.harness.events import LOG_VERSION, EventLog
from browser_agent.harness.llm import (
    BudgetExceededError,
    LLMClient,
    Message,
    ModelError,
    Part,
    Reply,
    ToolCall,
    ToolMessage,
    Usage,
    UserMessage,
)
from browser_agent.harness.tools import (
    FINISH_TOOL,
    TOOLS,
    FinishArgs,
    PageView,
    ToolExecutor,
    ToolOutcome,
    ToolSpec,
)

_PROMPT_HEAD = """\
You are a web agent. You complete one task on a website by calling tools, and you \
end by calling finish.

What you see
- The last message shows the current page, your working note and the step count. \
Only the current page is shown: pages from earlier steps are gone.
- Before it comes the history: each of your earlier tool calls with a short result.
- The page is an outline of its accessibility tree. Elements you can act on start \
with a number in brackets, as in `[12] button "Save"`, followed by state such as \
value, checked or expanded. Indentation shows nesting. The outline covers the whole \
page, including parts below the visible area.
- Use the number in brackets as `ref`. Refs are valid only for the page shown now.

Working
- Reply with tool calls only. Do not write explanations.
"""

# The same section when every step's page is kept in the conversation.
_PROMPT_HEAD_WITH_PAGES = """\
You are a web agent. You complete one task on a website by calling tools, and you \
end by calling finish.

What you see
- After every step you get the page as it is then, your working note and the step \
count. Pages from earlier steps stay above in the conversation; the last message is \
the current page.
- The page is an outline of its accessibility tree. Elements you can act on start \
with a number in brackets, as in `[12] button "Save"`, followed by state such as \
value, checked or expanded. Indentation shows nesting. The outline covers the whole \
page, including parts below the visible area.
- Use the number in brackets as `ref`. Refs come from the latest page; older ones may \
no longer exist.

Working
- Reply with tool calls only. Do not write explanations.
"""

_ONE_CALL = "- Send one tool call per reply.\n"
_SEVERAL_CALLS = (
    "- You may send several tool calls in one reply when they all act on the page shown "
    "now, for example to fill several fields. They run in order and stop at the first "
    "one that fails or loads a new page.\n"
)

_PROMPT_TAIL = """\
- When the page shows something you will need later (a value to report, an id, how \
far you are through a list), save it with write_note before leaving the page. The \
note replaces the old one, so keep in it what is still needed.
- Work only on the site the task starts on, and stay signed in.
- Do not change data unless the task asks for it. Do not download files.
- Work on your own; nobody can answer questions during the task.
- When an action fails, read the error and try another way instead of repeating it.
- A long list is shortened and says how many items are not shown. To look for one \
of them, call read_page with find: it searches the whole page, hidden items included. \
Use the site's own search, filters and sorting when the list continues on more pages.
- A search or filter that finds nothing does not prove the thing is missing. Try part \
of the value or another spelling, or look through the list itself, before you report \
NOT_FOUND_ERROR.

Finishing
Call finish with:
- task_type: RETRIEVE when the task asks for information, MUTATE when it asks to \
create, change or delete something, NAVIGATE when it asks to show a page or a search \
result.
- status: SUCCESS when the objective is fully achieved. Otherwise NOT_FOUND_ERROR \
(the thing asked about does not exist), ACTION_NOT_ALLOWED_ERROR (the site does not \
support the action), PERMISSION_DENIED_ERROR, DATA_VALIDATION_ERROR (required input \
is missing or invalid) or UNKNOWN_ERROR.
- retrieved_data: for RETRIEVE, a JSON array written as a string, even for a single \
value. Use plain values (strings, numbers, booleans) unless the task asks for named \
fields, in which case use objects with exactly those fields. Use numbers for counts \
and amounts. For MUTATE and NAVIGATE use null.
- error_details: null on SUCCESS, otherwise a short reason.
For NAVIGATE, the requested page must be the one open when you call finish.
"""


def system_prompt(multi_action: bool, pages_in_history: bool = False) -> str:
    """The system prompt. It depends only on run settings, never on the step."""
    head = _PROMPT_HEAD_WITH_PAGES if pages_in_history else _PROMPT_HEAD
    return head + (_SEVERAL_CALLS if multi_action else _ONE_CALL) + _PROMPT_TAIL


NUDGE = "Reply with a tool call. Call finish when the task is done or cannot be done."
# Shown in place of an empty note. Models left the note unused and then went back and
# forth between pages they could no longer remember.
EMPTY_NOTE = "(empty: save here with write_note what you will need after leaving this page)"
EXTRA_CALL = "Not executed: only one tool call runs per step. Send it again if still needed."
AFTER_FAILURE = "Not executed: an earlier call in this step failed."
AFTER_NAVIGATION = (
    "Not executed: an earlier call in this step loaded a new page, so refs from the "
    "old page are gone. Look at the page now shown and send the call again if needed."
)
BAD_ARGUMENTS = "The arguments were not a JSON object. Send the call again with valid JSON."
# The tool result of the first finish when verify_before_finish is on. It is the
# same text for every task: it is built from nothing but the fact that finish was
# called, so nothing of the task's expected answer or type can leak into it.
CHECK_REQUEST = (
    "Not finished yet: check your answer once against the page now shown, then call "
    "finish again.\n"
    "- If you report an action as done, look for the evidence on the page: a success "
    "message, the item gone, the field showing the new value. If the evidence is "
    "missing, do the action now.\n"
    "- If your answer holds numbers or a list, recount or reread them from the page, "
    "preferably with read_page and find, or on a report page, not from memory.\n"
    "The next finish ends the task, with the answer you give then."
)
LESSONS_HEAD = "Lessons from earlier failed attempts on pages like this one:"
# Given a page's address, the lessons to show there: (id with version, text).
LessonsAt = Callable[[str], Sequence[tuple[str, str]]]
# How the event log names the reason a call was not run.
_SKIP_REASONS = {
    EXTRA_CALL: "single_action",
    AFTER_FAILURE: "after_failure",
    AFTER_NAVIGATION: "after_navigation",
}


@dataclass(frozen=True)
class Budgets:
    """Limits of one task. Whichever runs out first ends the task."""

    max_steps: int = 30
    max_tokens: int = 1_000_000
    max_seconds: float = 900.0
    max_usd: float = 2.0


@dataclass(frozen=True)
class LoopConfig:
    budgets: Budgets = field(default_factory=Budgets)
    # The same calls this many times in a row count as stuck.
    repeat_limit: int = 3
    # So does a page that has not changed for this many steps.
    unchanged_limit: int = 4
    # After this many hints, being stuck again ends the task.
    max_stuck_hints: int = 2
    # This many failed steps in a row send the agent back to the last page that worked.
    failure_limit: int = 3
    # Run every tool call of a reply, in order, instead of only the first.
    multi_action: bool = False
    # Keep every step's page in the history instead of showing only the current one.
    # This is the behaviour before the cache-friendly layout: the prompt grows by a
    # whole page per step. It exists as the "full history" arm of experiments.
    pages_in_history: bool = False
    # Hold back the first finish of a task once and ask the model to check its answer
    # against the page. The second finish ends the task as it is.
    verify_before_finish: bool = False
    # The tools offered to the model. Memory adds two; without it this is TOOLS.
    tools: tuple[ToolSpec, ...] = TOOLS
    # Long-term memory. The prefix (skills and site facts) is one message in front of
    # the task, the same for every step of every task of a run, so it stays in the
    # cached part of the prompt. Lessons depend on the page and go into the tail.
    # Both are absent unless a run config switches memory on.
    memory_prefix: str | None = None
    lessons_at: LessonsAt | None = None


@dataclass(frozen=True)
class RunResult:
    """How a task ended and what it cost."""

    # finished | budget_steps | budget_tokens | budget_time | budget_usd | stuck |
    # spend_cap | model_error | model_refusal
    reason: str
    finish: FinishArgs | None
    forced: bool
    steps: int
    usage: Usage
    cost_usd: float
    seconds: float
    error: str | None = None
    # Estimated prompt tokens by section, summed over the task's calls.
    sections: dict[str, int] = field(default_factory=dict)
    # Model calls answered from the development response cache, at no cost.
    replayed_calls: int = 0


def _call_key(calls: Sequence[ToolCall]) -> str:
    return json.dumps([[call.name, call.arguments] for call in calls], sort_keys=True)


class AgentLoop:
    """Runs one task to its end."""

    def __init__(
        self,
        llm: LLMClient,
        executor: ToolExecutor,
        events: EventLog,
        config: LoopConfig | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._llm = llm
        self._executor = executor
        self._events = events
        self._config = config or LoopConfig()
        self._clock = clock
        self._system = system_prompt(self._config.multi_action, self._config.pages_in_history)
        self._task = UserMessage("", section="task")
        prefix = self._config.memory_prefix
        self._memory = [UserMessage(prefix, section="memory")] if prefix else []
        self._lessons_logged: set[str] = set()
        # Append-only: an entry is never changed or removed once it is in.
        self._history: list[Message] = []
        self._note = ""
        self._usage = Usage()
        self._cost = 0.0
        self._sections: dict[str, int] = {}
        self._replayed = 0
        self._steps = 0
        self._started = 0.0
        # The answer of the finish that was held back for the check, if one was.
        self._held_back: FinishArgs | None = None

    def run(self, goal: str) -> RunResult:
        config = self._config
        self._started = self._clock()
        self._task = UserMessage(f"Task: {goal}", section="task")
        view = self._executor.view()
        self._events.append(
            "task_start",
            goal=goal,
            url=view.url,
            budgets=asdict(config.budgets),
            log_version=LOG_VERSION,
        )

        last_key: str | None = None
        repeats = 0
        last_fingerprint = view.fingerprint
        unchanged = 0
        failures = 0
        stuck_hints = 0
        stable_url = view.url
        status: list[str] = []
        detail: str | None = None

        while True:
            exhausted = self._exhausted_budget()
            if exhausted is not None:
                return self._force_finish(exhausted, view)

            self._steps += 1
            try:
                reply = self._call_model(view, status, detail, forced=False)
            except BudgetExceededError as exc:
                return self._end("spend_cap", error=str(exc))
            except ModelError as exc:
                return self._model_failed("model_error", exc)
            status, detail = [], None
            if reply.stop_reason == "refusal":
                return self._end("model_refusal", error="the model declined to continue")
            if not reply.tool_calls:
                self._events.append("nudge", step=self._steps, detail="no tool call")
                status = [NUDGE]
                continue

            outcomes = self._run_calls(reply.tool_calls)
            for outcome in outcomes:
                if outcome.finish is not None:
                    return self._end("finished", finish=outcome.finish)
                if outcome.note is not None:
                    self._note = outcome.note
                if outcome.detail is not None:
                    detail = outcome.detail
            view = self._executor.view()

            if any(not outcome.ok for outcome in outcomes):
                failures += 1
                if failures >= config.failure_limit and stable_url:
                    recovered = self._executor.recover(stable_url)
                    self._events.append(
                        "recovery", step=self._steps, detail=stable_url, ok=recovered.ok
                    )
                    status.append(f"{failures} steps in a row failed. {recovered.summary}")
                    failures = 0
                    view = self._executor.view()
            else:
                failures = 0
                if any(outcome.acted for outcome in outcomes):
                    stable_url = view.url or stable_url

            key = _call_key(reply.tool_calls)
            repeats = repeats + 1 if key == last_key else 1
            last_key = key
            if view.fingerprint == last_fingerprint:
                unchanged += 1
            else:
                unchanged = 0
                last_fingerprint = view.fingerprint

            stuck = None
            if repeats >= config.repeat_limit:
                stuck = f"the same call was made {repeats} times in a row"
            elif unchanged >= config.unchanged_limit:
                stuck = f"the page has not changed for {unchanged} steps"
            if stuck is not None:
                stuck_hints += 1
                repeats = unchanged = 0
                self._events.append("stuck", step=self._steps, detail=stuck)
                if stuck_hints > config.max_stuck_hints:
                    return self._force_finish("stuck", view)
                status.append(
                    f"You seem stuck: {stuck}. Change strategy: use a different element, "
                    "a different page or the site's search, or finish with the status "
                    "that fits if the task cannot be done."
                )

    # -- the prompt --------------------------------------------------------

    def _messages(self, view: PageView, status: Sequence[str], detail: str | None) -> list[Message]:
        """Task, history, then the tail: everything that changes from step to step."""
        tail = [Part("observation", f"Current page:\n{view.text}")]
        if detail is not None:
            tail.append(Part("observation", f"Detail you asked for:\n{detail}"))
        lessons = self._lessons(view)
        if lessons:
            listed = "\n".join(f"- {text}" for _, text in lessons)
            tail.append(Part("lessons", f"{LESSONS_HEAD}\n{listed}"))
        tail.append(Part("notes", f"Working note:\n{self._note or EMPTY_NOTE}"))
        lines = [f"Step {self._steps} of {self._config.budgets.max_steps}.", *status]
        tail.append(Part("status", "\n".join(lines)))
        if self._config.pages_in_history:
            # The page becomes part of the history and is sent again at every step.
            self._history.append(UserMessage(tail))
            return [*self._memory, self._task, *self._history]
        return [*self._memory, self._task, *self._history, UserMessage(tail)]

    def _lessons(self, view: PageView) -> Sequence[tuple[str, str]]:
        """The lessons for the page shown; each is logged the first time it appears."""
        if self._config.lessons_at is None:
            return ()
        lessons = self._config.lessons_at(view.url)
        for label, _ in lessons:
            if label not in self._lessons_logged:
                self._lessons_logged.add(label)
                self._events.append("lesson_shown", step=self._steps, lesson=label, url=view.url)
        return lessons

    # -- pieces of a step --------------------------------------------------

    def _call_model(
        self, view: PageView, status: Sequence[str], detail: str | None, forced: bool
    ) -> Reply:
        self._events.append(
            "observation",
            step=self._steps,
            url=view.url,
            title=view.title,
            chars=len(view.text),
            text=view.text,
            note=self._note,
            status=list(status),
        )
        completion = self._llm.complete(
            self._system, self._messages(view, status, detail), self._config.tools
        )
        reply = completion.reply
        self._usage = self._usage + reply.usage
        self._cost += completion.cost_usd
        for name, tokens in completion.sections.items():
            self._sections[name] = self._sections.get(name, 0) + tokens
        self._replayed += completion.from_cache
        self._events.append(
            "model_call",
            step=self._steps,
            forced=forced,
            text=reply.text,
            tool_calls=[{"name": c.name, "arguments": c.arguments} for c in reply.tool_calls],
            stop_reason=reply.stop_reason,
            usage=asdict(reply.usage),
            sections=completion.sections,
            cost_usd=completion.cost_usd,
            seconds=round(completion.seconds, 3),
            attempts=completion.attempts,
            retry_errors=list(completion.retry_errors),
        )
        for fallback in reply.fallbacks:
            kind, _, change = fallback.partition(": ")
            self._events.append("provider_fallback", step=self._steps, fallback=kind, detail=change)
        self._history.append(reply.message())
        return reply

    def _model_failed(self, reason: str, exc: ModelError, forced: bool = False) -> RunResult:
        """End the task on a model error, leaving how many attempts it took in the log."""
        self._events.append(
            "model_error", step=self._steps, attempts=exc.attempts, error=str(exc)[:300]
        )
        return self._end(reason, forced=forced, error=str(exc))

    def _run_calls(self, calls: Sequence[ToolCall]) -> list[ToolOutcome]:
        """Run the calls of one reply in order and put each result into the history.

        A later call may rely on the page the earlier ones left, so the rest are
        skipped once a call fails or replaces the page.
        """
        outcomes: list[ToolOutcome] = []
        skip_reason: str | None = None
        for index, call in enumerate(calls):
            if skip_reason is None and index > 0 and not self._config.multi_action:
                skip_reason = EXTRA_CALL
            if skip_reason is not None:
                self._history.append(ToolMessage(call.id, skip_reason, is_error=True))
                self._events.append(
                    "tool_skipped",
                    step=self._steps,
                    name=call.name,
                    reason=_SKIP_REASONS[skip_reason],
                )
                continue
            outcome = self._run_tool(call)
            outcomes.append(outcome)
            self._history.append(ToolMessage(call.id, outcome.summary, is_error=not outcome.ok))
            if outcome.finish is not None:
                break
            if not outcome.ok:
                skip_reason = AFTER_FAILURE
            elif outcome.navigated:
                skip_reason = AFTER_NAVIGATION
        return outcomes

    def _run_tool(self, call: ToolCall, forced: bool = False) -> ToolOutcome:
        self._events.append("tool_call", step=self._steps, name=call.name, arguments=call.arguments)
        if call.arguments is None:
            outcome = ToolOutcome(False, BAD_ARGUMENTS)
        else:
            outcome = self._executor.execute(call.name, call.arguments)
        if outcome.finish is not None and self._check_is_due(forced):
            # The request travels as this call's result: the history only grows at
            # its end, and the system prompt and the tool list stay as they are.
            self._held_back = outcome.finish
            self._events.append("self_check", step=self._steps, first=outcome.finish.response())
            outcome = ToolOutcome(True, CHECK_REQUEST)
        self._events.append(
            "tool_result",
            step=self._steps,
            name=call.name,
            ok=outcome.ok,
            navigated=outcome.navigated,
            content=outcome.summary,
        )
        return outcome

    def _check_is_due(self, forced: bool) -> bool:
        """Once per task, and never on a finish the harness itself demanded."""
        return self._config.verify_before_finish and not forced and self._held_back is None

    def _exhausted_budget(self) -> str | None:
        budgets = self._config.budgets
        if self._steps >= budgets.max_steps:
            return "budget_steps"
        if self._usage.total_tokens >= budgets.max_tokens:
            return "budget_tokens"
        if self._clock() - self._started >= budgets.max_seconds:
            return "budget_time"
        if self._cost >= budgets.max_usd:
            return "budget_usd"
        return None

    def _force_finish(self, reason: str, view: PageView) -> RunResult:
        """Give the model one last call, in which only finish is accepted.

        The tool list stays as it is, because changing it would discard the cached
        prompt. A task budget is therefore soft by one call; the spend cap in the
        ledger is the hard limit and still applies to this call.
        """
        what = {
            "budget_steps": "step budget is",
            "budget_tokens": "token budget is",
            "budget_time": "time budget is",
            "budget_usd": "cost budget is",
            "stuck": "attempts to make progress are",
        }[reason]
        self._events.append("budget", step=self._steps, detail=reason)
        instruction = (
            f"The {what} used up. Call finish now; any other tool call is ignored. If the "
            "objective was achieved, report it; if not, use the status that fits and "
            "explain in error_details."
        )
        self._steps += 1
        try:
            reply = self._call_model(view, [instruction], None, forced=True)
        except BudgetExceededError as exc:
            return self._end(reason, forced=True, error=str(exc))
        except ModelError as exc:
            return self._model_failed(reason, exc, forced=True)
        for call in reply.tool_calls:
            if call.name == FINISH_TOOL.name and call.arguments is not None:
                outcome = self._run_tool(call, forced=True)
                if outcome.finish is not None:
                    return self._end(reason, finish=outcome.finish, forced=True)
        return self._end(reason, forced=True, error="no finish call after the budget ran out")

    def _end(
        self,
        reason: str,
        finish: FinishArgs | None = None,
        forced: bool = False,
        error: str | None = None,
    ) -> RunResult:
        kept_first = finish is None and self._held_back is not None
        if kept_first:
            # The task ended during the check without a second finish. The answer
            # the model had already given stands, rather than no answer at all.
            finish = self._held_back
        result = RunResult(
            reason=reason,
            finish=finish,
            forced=forced,
            steps=self._steps,
            usage=self._usage,
            sections=dict(self._sections),
            replayed_calls=self._replayed,
            cost_usd=self._cost,
            seconds=self._clock() - self._started,
            error=error,
        )
        self._events.append(
            "task_end",
            reason=reason,
            forced=forced,
            error=error,
            response=finish.response() if finish else None,
            kept_first_finish=kept_first,
            steps=result.steps,
            usage=asdict(result.usage),
            sections=result.sections,
            cost_usd=result.cost_usd,
            seconds=round(result.seconds, 3),
        )
        return result
