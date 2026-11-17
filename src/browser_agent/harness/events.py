"""Append-only event log of one task, and a replay that rebuilds its steps.

The log is the record of truth for a run: per-task numbers in the results are
recomputed from it, so a number can always be traced back to the events behind it.

Besides the steps (observation, model_call, tool_call, tool_result) the log holds
every fallback the harness took (nudge, tool_skipped, stuck, recovery, budget,
page_read_retry, settle_timeout, provider_fallback, model_error, self_check,
harness_error) and the score (task_scored). eval/fallbacks.py counts them.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Written into task_start. Version 2 added the events for fallbacks that used to
# leave no trace (busy-page retries, settle timeouts, provider downgrades, the
# reason a call was skipped) and the score. Version 3 added new_tab and the
# environment check before a task (env_repaired, browser_restarted). Version 4 added
# the events of long-term memory (skill_loaded, gate_passed, gate_rejected,
# skill_code_run, skill_step_failed, skill_guided, lesson_shown). A log without it is
# version 1.
LOG_VERSION = 4

# The shape of EventLog.append, for the parts of the harness that only report.
Notify = Callable[..., Any]


class EventLog:
    """Writes events to a JSON-lines file, one per line, never rewriting a line."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.events: list[dict[str, Any]] = []
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                raise FileExistsError(f"{path} exists; an event log is never overwritten")
            path.touch()

    @classmethod
    def resume(cls, path: Path) -> EventLog:
        """Continue the log at path, creating it if the task never got to write one.

        For what is only known after the loop has ended: the score, or the error
        that stopped the harness.
        """
        if not path.exists():
            return cls(path)
        log = cls()
        log.path = path
        log.events = read_events(path)
        return log

    def append(self, kind: str, **payload: Any) -> dict[str, Any]:
        event = {
            "seq": len(self.events),
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "type": kind,
            **payload,
        }
        self.events.append(event)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event


def read_events(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


@dataclass
class ToolStep:
    name: str
    arguments: Any
    ok: bool | None = None
    content: str | None = None


@dataclass
class Step:
    """One turn of the loop: a model call and the tool calls it led to."""

    index: int
    text: str = ""
    # The page the model was shown at this step. The prompt keeps no old pages, so
    # the log is the only place they can be read back from.
    page: str = ""
    url: str = ""
    forced: bool = False
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    tools: list[ToolStep] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class Replay:
    """The step sequence and totals rebuilt from a log."""

    goal: str = ""
    steps: list[Step] = field(default_factory=list)
    finish_reason: str | None = None
    response: dict[str, Any] | None = None
    total_tokens: int = 0
    cost_usd: float = 0.0

    def actions(self) -> list[tuple[str, Any]]:
        """The tool calls in order, enough to run the same task again by hand."""
        return [(tool.name, tool.arguments) for step in self.steps for tool in step.tools]


def replay(events: Iterable[dict[str, Any]]) -> Replay:
    """Rebuild the step sequence of a task from its events."""
    result = Replay()
    current: Step | None = None
    shown: dict[str, Any] = {}
    for event in events:
        kind = event["type"]
        if kind == "task_start":
            result.goal = event.get("goal", "")
        elif kind == "observation":
            shown = event
        elif kind == "model_call":
            current = Step(
                index=event["step"],
                text=event.get("text", ""),
                page=shown.get("text", ""),
                url=shown.get("url", ""),
                forced=event.get("forced", False),
                usage=event.get("usage", {}),
                cost_usd=event.get("cost_usd", 0.0),
            )
            result.steps.append(current)
            result.total_tokens += sum(current.usage.values())
            result.cost_usd += current.cost_usd
        elif kind == "tool_call" and current is not None:
            current.tools.append(ToolStep(event["name"], event.get("arguments")))
        elif kind == "tool_result" and current is not None and current.tools:
            current.tools[-1].ok = event.get("ok")
            current.tools[-1].content = event.get("content")
        elif kind in ("stuck", "recovery", "nudge") and current is not None:
            current.notes.append(f"{kind}: {event.get('detail', '')}")
        elif kind == "task_end":
            result.finish_reason = event.get("reason")
            result.response = event.get("response")
    return result
