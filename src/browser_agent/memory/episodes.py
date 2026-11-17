"""Learn episodes, read back from the traces of earlier runs.

Memory is built from what the agent did on the learn tasks. An episode here is one
task of one run: what was asked, each step with the element it acted on (by role and
name, as the page showed it), the pages, the agent's own final answer, and whether the
official evaluator scored it successful. Nothing else of the evaluator is read: not
the expected answer, not its details.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from browser_agent.harness.events import read_events

_SLOT = re.compile(r"\{\{(\w+)\}\}")
# Slots that say how the answer is to be laid out. They are the same for every task
# of a template in effect, and a skill keeps that layout fixed.
FORMAT_SLOTS = frozenset({"retrieved_data_format_spec"})
_SITE_BASE = re.compile(r"https?://[^/\s\"')]+/admin(?![\w-])")
_REF = re.compile(r"\[\d+\] ?")
_MAX_PAGE_CHARS = 6000


def without_site(text: str) -> str:
    """Addresses made relative to the site, so nothing of one machine's setup is kept."""
    return _SITE_BASE.sub("", text)


def without_refs(text: str) -> str:
    """Refs belong to one page load and mean nothing afterwards."""
    return _REF.sub("", text)


# Free text of this length is a message or a title, not the name of an option.
_LONG_VALUE_CHARS = 25


def names_an_instance(value: str, quoted: bool = False) -> bool:
    """Whether a task value names one particular thing, as opposed to a kind of thing.

    "302", "March 31, 2022", "Jane Doe" and a message text name an instance; a skill
    that carries one of them was written for that task only. "orders", "Reduce" and
    "so far" name a kind: a skill has to mention such words to say what each choice
    means, and whether the choice is a parameter is checked separately.
    """
    text = value.strip()
    if len(text) < 3:
        return False
    words = text.split()
    proper_name = len(words) >= 2 and all(word[:1].isupper() for word in words)
    has_digit = any(char.isdigit() for char in text)
    return quoted or has_digit or proper_name or len(text) >= _LONG_VALUE_CHARS


def quoted_slots(template: str) -> set[str]:
    """Slots the template puts in quotation marks: free text given word for word."""
    return {
        slot.group(1)
        for slot in _SLOT.finditer(template)
        if template[: slot.start()].endswith('"') and template[slot.end() :].startswith('"')
    }


def match_slots(template: str, intent: str) -> dict[str, str] | None:
    """The text a task puts into each {{slot}} of its template, or None if it does not fit.

    The slots are exactly what differs between the tasks of one template, so they are
    what a skill must take as parameters and must not carry as fixed text.
    """
    if not template:
        return None
    pattern, position = "", 0
    for slot in _SLOT.finditer(template):
        pattern += re.escape(template[position : slot.start()])
        pattern += f"(?P<{slot.group(1)}>.*?)"
        position = slot.end()
    pattern += re.escape(template[position:])
    matched = re.fullmatch(pattern, intent.strip(), flags=re.DOTALL)
    if matched is None:
        return None
    return {name: value.strip() for name, value in matched.groupdict().items()}


@dataclass(frozen=True)
class EpisodeStep:
    """One tool call of an episode, with the page it was made on."""

    number: int
    # Address of the page the call was made on, relative to the site.
    path: str
    title: str
    # The page as the agent was shown it.
    page: str
    call: str
    arguments: dict[str, Any]
    # The element the call acted on, as the page listed it: role "name", and its row.
    element: str
    result: str
    ok: bool


@dataclass(frozen=True)
class Episode:
    """One task of one run."""

    run: str
    task_id: int
    template_id: int
    task_type: str
    state_changing: bool
    intent: str
    success: bool
    finish_reason: str
    steps: list[EpisodeStep] = field(repr=False)
    # The agent's own final answer (its finish arguments), not the expected one.
    answer: dict[str, Any] | None = None
    # The page the agent was on when the episode ended, and its address.
    final_path: str = ""
    final_page: str = field(default="", repr=False)
    # The template of the task and what this task put into its slots. This is dataset
    # metadata of a learn task; empty when the task's text does not fit its template.
    intent_template: str = ""
    slots: dict[str, str] = field(default_factory=dict)

    def value_slots(self) -> dict[str, str]:
        """The slots that carry a value of the task: not the answer format, not empty."""
        return {
            name: value for name, value in self.slots.items() if name not in FORMAT_SLOTS and value
        }

    def literals(self) -> list[str]:
        """Text that memory built from this episode must not carry: the task's values.

        Each slot value that names an instance, as a whole, and every number of three
        or more digits in it (the task says "order 302", the pages show 000000302).
        Values that name a kind of thing are not in the list; see names_an_instance.
        """
        found: set[str] = set()
        quoted = quoted_slots(self.intent_template)
        for name, value in self.value_slots().items():
            if names_an_instance(value, quoted=name in quoted):
                found.add(value)
            found.update(re.findall(r"\d{3,}", value))
        return sorted(found)

    @property
    def key(self) -> str:
        return f"{self.run}/{self.task_id}"

    def calls(self) -> int:
        return len(self.steps)

    def page_text(self) -> str:
        """Everything the agent was shown in this episode, for checks on what it saw."""
        return "\n".join([*(step.page for step in self.steps), self.final_page])

    def source(self) -> dict[str, Any]:
        return {"run": self.run, "task_id": self.task_id, "template_id": self.template_id}

    def render(self, with_pages: bool = True, with_template: bool = False) -> str:
        """The episode as text for a model: the task, then every step in order."""
        lines = [f"Task: {self.intent}"]
        if with_template and self.slots:
            lines.append(f"Task template: {self.intent_template}")
            filled = "; ".join(f"{name} = {value!r}" for name, value in self.value_slots().items())
            lines.append(f"Slots in this task: {filled or 'none'}")
        lines.append("")
        for step in self.steps:
            lines.append(f"Step {step.number}. On page {step.path} (title: {step.title})")
            if with_pages:
                lines += ["  The page showed:", *_indented(_cut(without_refs(step.page)))]
            arguments = {key: value for key, value in step.arguments.items() if key != "ref"}
            lines.append(f"  Call: {step.call} {json.dumps(arguments, ensure_ascii=False)}")
            if step.element:
                lines.append(f"  Element: {step.element}")
            outcome = "Result" if step.ok else "Result (the call failed)"
            lines.append(f"  {outcome}: {without_refs(step.result)}")
            lines.append("")
        if self.final_page:
            lines.append(f"At the end the agent was on page {self.final_path}")
            if with_pages:
                lines += ["  The page showed:", *_indented(_cut(without_refs(self.final_page)))]
            lines.append("")
        if self.answer is not None:
            lines.append(f"The agent's final answer: {json.dumps(self.answer, ensure_ascii=False)}")
        return "\n".join(lines).rstrip() + "\n"


def _cut(text: str) -> str:
    if len(text) <= _MAX_PAGE_CHARS:
        return text
    return f"{text[:_MAX_PAGE_CHARS]}\n[... {len(text) - _MAX_PAGE_CHARS} more characters]"


def _indented(text: str) -> list[str]:
    return [f"    {line}" for line in text.splitlines()]


def element_on_page(page: str, ref: Any) -> str:
    """How a page listed the element behind a ref: role, name and the row it is in."""
    if not isinstance(ref, int):
        return ""
    for line in page.splitlines():
        match = re.search(rf'\[{ref}\] ([\w-]+)(?: ("(?:[^"\\]|\\.)*"))?', line)
        if match is None:
            continue
        element = match.group(1) + (f" {match.group(2)}" if match.group(2) else "")
        row = re.match(r"\s*\[\d+\] row: (.*)", line)
        if row is not None and not line.lstrip().startswith(f"[{ref}]"):
            return f"{element}, in the table row: {without_refs(row.group(1))[:200]}"
        return element
    return ""


def load_episode(run_dir: Path, record: dict[str, Any], entry: dict[str, Any]) -> Episode | None:
    """One task of a run, or None when the run kept no trace of it."""
    log = run_dir / "traces" / str(record["task_id"]) / "events.jsonl"
    if not log.exists():
        return None
    steps: list[EpisodeStep] = []
    page: dict[str, Any] = {}
    pending: dict[str, Any] | None = None
    answer = None
    for event in read_events(log):
        kind = event["type"]
        if kind == "observation":
            page = event
        elif kind == "tool_call":
            pending = event
        elif kind == "tool_result" and pending is not None:
            arguments = pending.get("arguments")
            arguments = arguments if isinstance(arguments, dict) else {}
            text = without_site(page.get("text", ""))
            if pending["name"] != "finish":
                steps.append(
                    EpisodeStep(
                        number=len(steps) + 1,
                        path=without_site(page.get("url", "")) or "/",
                        title=page.get("title", ""),
                        page=text,
                        call=pending["name"],
                        arguments=arguments,
                        element=element_on_page(text, arguments.get("ref")),
                        result=without_site(event.get("content") or ""),
                        ok=bool(event.get("ok")),
                    )
                )
            pending = None
        elif kind == "task_end":
            answer = event.get("response")
    return Episode(
        run=run_dir.name,
        task_id=int(record["task_id"]),
        template_id=int(record["template_id"]),
        task_type=str(entry.get("task_type", record.get("task_type", ""))),
        state_changing=bool(entry.get("state_changing", record.get("state_changing", True))),
        intent=str(entry.get("intent", "")),
        success=bool(record["success"]),
        finish_reason=str(record.get("finish_reason", "")),
        steps=steps,
        answer=answer,
        final_path=without_site(page.get("url", "")) or "/",
        final_page=without_site(page.get("text", "")),
        intent_template=str(entry.get("intent_template", "")),
        slots=match_slots(str(entry.get("intent_template", "")), str(entry.get("intent", "")))
        or {},
    )


def load_episodes(results: Path, runs: list[str], entries: list[dict[str, Any]]) -> list[Episode]:
    """Every episode of the named runs that belongs to one of the given tasks."""
    by_task = {int(entry["task_id"]): entry for entry in entries}
    episodes = []
    for run in runs:
        run_dir = results / run
        with (run_dir / "records.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                entry = by_task.get(int(record["task_id"]))
                if entry is None:
                    continue
                episode = load_episode(run_dir, record, entry)
                if episode is not None:
                    episodes.append(episode)
    return episodes


def shortest_successes(episodes: list[Episode]) -> dict[int, Episode]:
    """Per template, the successful episode with the fewest calls; none if it never succeeded.

    Ties go to the episode that comes first, so the choice does not depend on chance.
    """
    best: dict[int, Episode] = {}
    for episode in episodes:
        if not episode.success or not episode.steps:
            continue
        current = best.get(episode.template_id)
        if current is None or episode.calls() < current.calls():
            best[episode.template_id] = episode
    return dict(sorted(best.items()))


def failures(episodes: list[Episode]) -> list[Episode]:
    """Failed episodes that left a trace to reflect on."""
    return [episode for episode in episodes if not episode.success and episode.steps]
