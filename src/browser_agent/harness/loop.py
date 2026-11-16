"""The agent loop: one model call and one tool call per step, under budgets.

The loop knows nothing about browsers or providers. It talks to a ToolExecutor and
an LLMClient, which is what lets the tests drive it with scripted replies.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field

from browser_agent.harness.events import EventLog
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
    ToolExecutor,
    ToolOutcome,
    ToolSpec,
)

SYSTEM_PROMPT = """\
You are a web agent. You complete one task on a website by calling tools, one tool \
call per step, and you end by calling finish.

Reading the page
- After every action you receive the page as an outline of its accessibility tree. \
Each line is `[ref] role "name"` plus state such as value, checked or expanded. \
Indentation shows nesting.
- The outline covers the whole page, including parts below the visible area.
- Use the number in brackets as `ref`. Refs come from the latest page text; older \
ones may no longer exist.

Acting
- Work only on the site the task starts on, and stay signed in.
- Do not change data unless the task asks for it. Do not download files.
- Work on your own; nobody can answer questions during the task.
- When an action fails, read the error and try another way instead of repeating it.
- Filters, sorting and search on the site are usually faster than reading long lists.

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

NUDGE = "Reply with a tool call. Call finish when the task is done or cannot be done."
EXTRA_CALL = "Not executed: only one tool call runs per step. Send it again if still needed."
BAD_ARGUMENTS = "The arguments were not a JSON object. Send the call again with valid JSON."


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
    # The same call this many times in a row counts as stuck.
    repeat_limit: int = 3
    # So does a page that has not changed for this many steps.
    unchanged_limit: int = 4
    # After this many hints, being stuck again ends the task.
    max_stuck_hints: int = 2
    # This many failed calls in a row send the agent back to the last page that worked.
    failure_limit: int = 3
    system_prompt: str = SYSTEM_PROMPT


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


MessageView = Callable[[Sequence[Message]], Sequence[Message]]


def _full_history(messages: Sequence[Message]) -> Sequence[Message]:
    return messages


def _call_key(call: ToolCall) -> str:
    return f"{call.name}:{json.dumps(call.arguments, sort_keys=True)}"


class AgentLoop:
    """Runs one task to its end.

    view_messages is the plug point for history components (compaction, working
    note): it maps the full history to what the model is shown. The default shows
    everything.
    """

    def __init__(
        self,
        llm: LLMClient,
        executor: ToolExecutor,
        events: EventLog,
        config: LoopConfig | None = None,
        view_messages: MessageView = _full_history,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._llm = llm
        self._executor = executor
        self._events = events
        self._config = config or LoopConfig()
        self._view = view_messages
        self._clock = clock
        self._messages: list[Message] = []
        self._usage = Usage()
        self._cost = 0.0
        self._sections: dict[str, int] = {}
        self._steps = 0
        self._started = 0.0

    def run(self, goal: str) -> RunResult:
        config = self._config
        self._started = self._clock()
        first = self._executor.read_page()
        self._messages = [
            UserMessage(
                [
                    Part("task", f"Task: {goal}"),
                    Part("observation", f"Current page:\n{first.content}"),
                ]
            )
        ]
        self._events.append("task_start", goal=goal, url=first.url, budgets=asdict(config.budgets))

        last_key: str | None = None
        repeats = 0
        last_fingerprint = first.fingerprint
        unchanged = 0
        failures = 0
        stuck_hints = 0
        stable_url = first.url

        while True:
            exhausted = self._exhausted_budget()
            if exhausted is not None:
                return self._force_finish(exhausted)

            self._steps += 1
            try:
                reply = self._call_model(TOOLS, forced=False)
            except BudgetExceededError as exc:
                return self._end("spend_cap", error=str(exc))
            except ModelError as exc:
                return self._end("model_error", error=str(exc))
            if reply.stop_reason == "refusal":
                return self._end("model_refusal", error="the model declined to continue")
            if not reply.tool_calls:
                self._events.append("nudge", step=self._steps, detail="no tool call")
                self._messages.append(UserMessage(NUDGE, section="status"))
                continue

            call, extra = reply.tool_calls[0], reply.tool_calls[1:]
            outcome = self._run_tool(call)
            if outcome.finish is not None:
                return self._end("finished", finish=outcome.finish)

            notes: list[str] = []
            if outcome.ok:
                failures = 0
                stable_url = outcome.url or stable_url
            else:
                failures += 1
                if failures >= config.failure_limit and stable_url:
                    recovered = self._executor.recover(stable_url)
                    self._events.append(
                        "recovery", step=self._steps, detail=stable_url, ok=recovered.ok
                    )
                    notes.append(f"{failures} tool calls in a row failed. {recovered.content}")
                    failures = 0

            key = _call_key(call)
            repeats = repeats + 1 if key == last_key else 1
            last_key = key
            # A failed call leaves the page as it was, so it counts as no change.
            if outcome.fingerprint is None or outcome.fingerprint == last_fingerprint:
                unchanged += 1
            else:
                unchanged = 0
                last_fingerprint = outcome.fingerprint

            stuck = None
            if repeats >= config.repeat_limit:
                stuck = f"the same call was made {repeats} times in a row"
            elif unchanged >= config.unchanged_limit:
                stuck = f"the page has not changed for {unchanged} steps"
            if stuck is not None:
                stuck_hints += 1
                repeats = unchanged = 0
                self._events.append("stuck", step=self._steps, detail=stuck)
                notes.append(
                    f"You seem stuck: {stuck}. Change strategy: use a different element, "
                    "a different page or the site's search, or finish with the status "
                    "that fits if the task cannot be done."
                )

            parts = [Part("observation", outcome.content)]
            parts += [Part("status", note) for note in notes]
            self._messages.append(ToolMessage(call.id, parts, is_error=not outcome.ok))
            for other in extra:
                self._messages.append(
                    ToolMessage(other.id, EXTRA_CALL, is_error=True, section="status")
                )
            if stuck is not None and stuck_hints > config.max_stuck_hints:
                return self._force_finish("stuck")

    # -- pieces of a step --------------------------------------------------

    def _call_model(self, tools: Sequence[ToolSpec], forced: bool) -> Reply:
        completion = self._llm.complete(
            self._config.system_prompt, self._view(self._messages), tools
        )
        reply = completion.reply
        self._usage = self._usage + reply.usage
        self._cost += completion.cost_usd
        for name, tokens in completion.sections.items():
            self._sections[name] = self._sections.get(name, 0) + tokens
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
        )
        self._messages.append(reply.message())
        return reply

    def _run_tool(self, call: ToolCall) -> ToolOutcome:
        self._events.append("tool_call", step=self._steps, name=call.name, arguments=call.arguments)
        if call.arguments is None:
            outcome = ToolOutcome(False, BAD_ARGUMENTS)
        else:
            outcome = self._executor.execute(call.name, call.arguments)
        self._events.append(
            "tool_result",
            step=self._steps,
            name=call.name,
            ok=outcome.ok,
            url=outcome.url,
            content=outcome.content,
        )
        return outcome

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

    def _force_finish(self, reason: str) -> RunResult:
        """Give the model one last call, with finish as its only tool.

        A task budget is therefore soft by one call; the spend cap in the ledger is
        the hard limit and still applies to this call.
        """
        what = {
            "budget_steps": "step budget is",
            "budget_tokens": "token budget is",
            "budget_time": "time budget is",
            "budget_usd": "cost budget is",
            "stuck": "attempts to make progress are",
        }[reason]
        self._events.append("budget", step=self._steps, detail=reason)
        self._messages.append(
            UserMessage(
                f"The {what} used up. Call finish now. If the objective was achieved, "
                "report it; if not, use the status that fits and explain in error_details.",
                section="status",
            )
        )
        self._steps += 1
        try:
            reply = self._call_model([FINISH_TOOL], forced=True)
        except BudgetExceededError as exc:
            return self._end(reason, forced=True, error=str(exc))
        except ModelError as exc:
            return self._end(reason, forced=True, error=str(exc))
        for call in reply.tool_calls:
            if call.name == FINISH_TOOL.name and call.arguments is not None:
                outcome = self._run_tool(call)
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
        result = RunResult(
            reason=reason,
            finish=finish,
            forced=forced,
            steps=self._steps,
            usage=self._usage,
            sections=dict(self._sections),
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
            steps=result.steps,
            usage=asdict(result.usage),
            cost_usd=result.cost_usd,
            seconds=round(result.seconds, 3),
        )
        return result
