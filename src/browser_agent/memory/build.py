"""Turn learn episodes into memory: skills, site facts and lessons.

Every item is written by a model call that sees one episode (or, for merging, the items
of one kind). What a call returns is checked here before it is stored: the skill format,
the sandbox rules for code, and that no literal value of the source task is left in a
skill. Skills and site facts come from episodes the evaluator scored successful,
lessons from failed ones; the calls are told only that outcome.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict

from browser_agent.harness.llm import LLMClient, ModelError, UserMessage
from browser_agent.harness.tools import ToolSpec
from browser_agent.memory.episodes import Episode, names_an_instance
from browser_agent.memory.locators import Locator
from browser_agent.memory.skill import (
    Check,
    Param,
    Skill,
    SkillFormatError,
    SkillMeta,
    check_code,
    parse_skill_md,
    render_skill_md,
)

MAX_ITEM_CHARS = 300
# "Cancel order 302": the pages show it as 000000302, so three digits already count.
_LONG_NUMBER = re.compile(r"\d{3,}")
_QUOTED = re.compile(r'"([^"]{4,})"')
_FORMAT_KEYS = re.compile(r"\bkeys?\b", re.IGNORECASE)


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    # Strict tool calling: every property required, nothing else allowed.
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


_STRING = {"type": "string"}
_OPTIONAL = {"type": ["string", "null"]}
_ARGS = {
    "type": "array",
    "items": _object(
        {
            "name": _STRING,
            "value": {
                "type": "string",
                "description": 'The value as JSON: "\\"000000123\\"", "5", "true".',
            },
        }
    ),
}
_LOCATOR = {"role": _STRING, "name": _STRING, "row": _OPTIONAL, "section": _OPTIONAL}

SAVE_SKILL = ToolSpec(
    "save_skill",
    "Save the skill written from the episode.",
    _object(
        {
            "name": {"type": "string", "description": "Lowercase words joined by hyphens."},
            "description": {
                "type": "string",
                "description": "One line, under 150 characters: what the skill does.",
            },
            "url_pattern": {
                "type": "string",
                "description": "Regular expression for the site-relative address of the pages "
                'the skill may be started on; "^/" when it begins with goto.',
            },
            "params": {
                "type": "array",
                "items": _object(
                    {
                        "name": _STRING,
                        "type": {
                            "type": "string",
                            "enum": ["string", "integer", "number", "boolean"],
                        },
                        "description": _STRING,
                        "slot": {
                            "type": ["string", "null"],
                            "description": "The slot of the task template whose value this "
                            "parameter carries; null only for a parameter no slot stands for.",
                        },
                    }
                ),
            },
            "required_elements": {
                "type": "array",
                "description": "Elements that must be on the page the skill is started on.",
                "items": _object(_LOCATOR),
            },
            "preconditions": {
                "type": "array",
                "description": "Each is exactly one of: text, url, or role with name.",
                "items": _object(
                    {
                        "text": _OPTIONAL,
                        "url": _OPTIONAL,
                        "role": _OPTIONAL,
                        "name": _OPTIONAL,
                        "row": _OPTIONAL,
                        "section": _OPTIONAL,
                        "why": _OPTIONAL,
                    }
                ),
            },
            "steps": {
                "type": "string",
                "description": "The body of SKILL.md: numbered steps, each with what to check "
                "after it, then known pitfalls.",
            },
            "code": {
                "type": ["string", "null"],
                "description": "The same steps as def run(...), or null if they cannot be "
                "written with the allowed calls.",
            },
            "source_args": {**_ARGS, "description": "The parameter values of the episode."},
            "other_args": {
                "type": "array",
                "description": "One or two other sets of parameter values, each using values "
                "that the episode's pages show.",
                "items": _object({"args": _ARGS, "seen": _STRING}),
            },
        }
    ),
    _Out,
)

_ITEMS = {
    "type": "array",
    "items": _object({"text": _STRING, "url_pattern": _STRING}),
}
SAVE_FACTS = ToolSpec(
    "save_facts", "Save the site facts found in the episode.", _object({"facts": _ITEMS}), _Out
)
SAVE_LESSONS = ToolSpec(
    "save_lessons", "Save the lessons of the failed episode.", _object({"lessons": _ITEMS}), _Out
)
MERGE_ITEMS = ToolSpec(
    "merge_items",
    "Save the merged list.",
    _object(
        {
            "items": {
                "type": "array",
                "items": _object(
                    {
                        "text": _STRING,
                        "url_pattern": _STRING,
                        "from": {"type": "array", "items": _STRING},
                    }
                ),
            }
        }
    ),
    _Out,
)

_ADDRESSES = """\
Addresses are always relative to the site: "/sales/order/", never with a host. A
url_pattern is a regular expression searched in that relative address."""

INDUCE_SYSTEM = f"""\
You write a reusable skill for a web agent from one episode in which the agent
completed a task on an online shop's admin site. The episode was scored successful.
Another task of the same kind, with other values, should be solvable by following
your skill. Reply by calling save_skill once.

A skill has two parts.

1. Steps in plain language (the field "steps"): numbered steps a careful person could
   follow, each saying what to do and what to check afterwards, then a short list of
   pitfalls seen in the episode (detours the agent took, things that are easy to get
   wrong). Leave out steps of the episode that were detours.

2. Code (the field "code"): the same steps as one Python function, def run(...), whose
   parameters are exactly the skill's parameters. Give null if the steps cannot be
   written with the calls below.

Parameters. With the episode you get the task template: the task text with its
slots marked as {{{{slot}}}}, and what this task put into each slot. The slots are
exactly what differs between the tasks of this kind.
- Every slot is carried by at least one parameter; name the slot in the parameter's
  "slot" field. A slot may need several parameters (a time span becomes a start and
  an end date). Never build the value of a slot into the skill: a skill with a slot
  fixed does the wrong thing on the next task and nobody notices.
- A slot whose values need different pages or different steps (which report, which
  attribute, which action) is still a parameter. In the steps, say how its value
  decides what to do, for the values the episode's pages show (menu entries, column
  names, options). In the code, use the parameter to choose (if/else, a locator named
  by the parameter); if the code cannot cover the slot, give no code (null).
- What this task put into a slot must not appear in the steps or in the code when it
  names one particular thing: a number, a date, a person, a product, a title, a
  message. Words that name a kind of thing (which report, which action) may appear
  where the steps or the code say what each choice means.
- Values that are the same for every task of this kind (a menu name, a button label)
  are written out. The layout of the answer that the task asks for is fixed, not a
  parameter.

Elements are named by locator, never by number: role and accessible name exactly as the
page lists them (role first, then the name in quotes), optionally with
- row: a text shown in the table row that holds the element (for example an order
  number), to pick one row of a table;
- section: the name of a named element that contains it, when two elements on the
  page have the same role and name.
A locator must match exactly one element, or the step fails.

{_ADDRESSES}

The calls available in code, and nothing else:
  goto(path)                                  open a site-relative address
  click(role=, name=, row=None, section=None)
  type(role=, name=, text=, row=None, section=None, submit=False)
                                              replace a field's content; submit=True
                                              presses Enter
  select(role=, name=, option=, row=None, section=None)
                                              choose an option of a dropdown by its label
  read(role=, name=, row=None, section=None)  the text of an element; for a table, a
                                              list of rows, each a list of cell texts
  check(text=)  or  check(url=)  or  check(role=, name=, row=None, section=None)
                                              stop unless the page shows the text, its
                                              address matches the pattern, or exactly
                                              one such element exists
  return_value(value)                         hand back what the task asked for

Rules for code. It is checked before it may run and refused if it breaks them.
- One function def run(...) and nothing else. No imports, no while, no nested
  functions, no try, no comprehensions, no attribute access except these methods:
  strip, split, lower, upper, replace, startswith, endswith, join, get, append, count,
  isdigit. Helpers: len, str, int, float, sorted, min, max, sum, range (up to 200),
  enumerate, zip, list, dict. for loops over lists (with break and continue) and if
  are allowed.
- After every goto, click, select and type(..., submit=True) there must be a check()
  before the next such call. Check something that shows the step worked and that the
  page is the right one: a heading, a field of the next form, a success message, the
  address. Use values of the parameters in checks where the page shows them.
- Prefer goto with an address the episode shows over clicking through menus.
- A skill does not finish the task. A skill for a question ends with return_value.
- When a table is read, the first row is the header row. Find a column by its header,
  not by a fixed position.

Starting point. url_pattern, required_elements and preconditions describe the page the
skill is started on and are checked before the code runs. If the code begins with
goto, use url_pattern "^/" and no required elements. If the task is about "the current
page", the skill starts there: give that page's address pattern and the elements the
first step needs.

Also return:
- source_args: the values of the parameters in this episode.
- other_args: two other sets of values to test the skill with, whenever the episode's
  pages show any. Every value must be one that those pages show: another row of the
  same table, another option of the same dropdown, another name or number in a list.
  In "seen", say where. The site is restored after every test, so a skill that changes
  data can be tested on any item the pages show. Give none only if the pages show no
  other usable values.
"""

FACTS_SYSTEM = f"""\
You read one episode in which a web agent completed a task on an online shop's admin
site; the episode was scored successful. Write down what it shows about the site that
would help with other tasks: where a page is, which report or filter gives what, how a
form or a table behaves. Reply by calling save_facts once.

- At most four facts, each one sentence, general and short.
- A fact is about the site, not about this task: no order numbers, names, dates or
  other values of the task.
- Only what the episode shows. Do not guess.
- Each fact has a url_pattern for the pages it is about.

{_ADDRESSES}
"""

LESSONS_SYSTEM = f"""\
You read one episode in which a web agent attempted a task on an online shop's admin
site. The episode was scored as failed. You are not told what the right result is.
From the episode alone, work out what most likely went wrong and write down what an
agent on the same pages should do differently. Reply by calling save_lessons once.

- At most two lessons, each one or two sentences, as an instruction ("On ..., do ...").
- A lesson is about how to work on those pages, not about this task: no order numbers,
  names, dates or other values of the task.
- If the episode does not show what went wrong, give no lesson.
- Each lesson has a url_pattern for the pages on which it should be shown.

{_ADDRESSES}
"""

MERGE_SYSTEM = """\
You get a numbered list of short notes about one web site, written separately from
different episodes. Many repeat each other. Merge those that say the same thing into
one note and keep the others as they are. Reply by calling merge_items once.

- Every note you return lists in "from" the ids of the notes it stands for. Every id
  of the input appears in exactly one returned note.
- Do not add anything the notes do not say. When two notes contradict each other, keep
  both, unmerged.
- A merged note keeps the most general url_pattern of its sources.
"""


class BuildError(RuntimeError):
    """A model call did not return what was asked for."""


def ask(llm: LLMClient, system: str, text: str, tool: ToolSpec) -> dict[str, Any]:
    """One model call that must answer with one call of the given tool."""
    try:
        completion = llm.complete(system, [UserMessage(text)], [tool])
    except ModelError as exc:
        # One refused or failed call costs one item, not the build.
        raise BuildError(f"the model call failed: {exc}") from exc
    for call in completion.reply.tool_calls:
        if call.name == tool.name and isinstance(call.arguments, dict):
            return call.arguments
    raise BuildError(
        f"the model did not call {tool.name} (stop reason {completion.reply.stop_reason!r})"
    )


# -- skills ----------------------------------------------------------------


@dataclass
class Candidate:
    """What induction produced for one template, after checking."""

    template_id: int
    source: dict[str, Any]
    # The skill as guidance (no code), or None when it was not usable at all.
    skill: Skill | None = None
    # Code that passed the sandbox rules and awaits verification.
    code: str | None = None
    source_args: dict[str, Any] = field(default_factory=dict)
    other_args: list[dict[str, Any]] = field(default_factory=list)
    # Why there is no skill; empty when there is one.
    rejected: list[str] = field(default_factory=list)
    # Why there is no code although the model wrote some.
    code_problems: list[str] = field(default_factory=list)
    # Which slot of the task template each parameter carries.
    param_slots: dict[str, str | None] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    attempts: int = 0


def _decode_args(pairs: Any) -> dict[str, Any]:
    args: dict[str, Any] = {}
    for pair in pairs or []:
        try:
            args[str(pair["name"])] = json.loads(pair["value"])
        except (TypeError, ValueError, KeyError):
            args[str(pair.get("name"))] = pair.get("value")
    return args


def task_literals(intent: str) -> list[str]:
    """Values in a task text that memory must not carry: numbers and quoted text.

    Quoted words after "keys" are left out: 'with keys "month" and "count"' names the
    fields of the answer, which are the same for every task of the kind, not values of
    this task. Treating them as values refused a skill for saying "count".
    """
    keys = _FORMAT_KEYS.search(intent)
    values_part = intent if keys is None else intent[: keys.start()]
    return sorted(set(_LONG_NUMBER.findall(intent)) | set(_QUOTED.findall(values_part)))


def episode_literals(episode: Episode) -> list[str]:
    """The task values memory must not carry: what the task put into its template's
    slots. Only when the task's text does not fit its template are they guessed from
    the text instead."""
    return episode.literals() if episode.slots else task_literals(episode.intent)


def uncovered_slots(param_slots: dict[str, str | None], episode: Episode) -> list[str]:
    """The value slots of the task's template that no parameter carries."""
    return sorted(set(episode.value_slots()) - {slot for slot in param_slots.values() if slot})


def _leaks(text: str, literals: Sequence[str]) -> list[str]:
    lowered = text.casefold()
    return [literal for literal in literals if literal.casefold() in lowered]


def _code_strings(code: str) -> str:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code
    return "\n".join(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    )


def check_candidate(
    raw: dict[str, Any], episode: Episode, excluded_texts: Sequence[str] = ()
) -> Candidate:
    """Check what induction returned. Problems with the skill itself reject it;
    problems with the code only leave the skill without code."""
    candidate = Candidate(episode.template_id, episode.source())
    try:
        meta = SkillMeta(
            name=raw["name"],
            description=raw["description"],
            version=1,
            params={
                item["name"]: Param(type=item["type"], description=item["description"])
                for item in raw["params"]
            },
            url_pattern=raw["url_pattern"],
            required_elements=[
                Locator(**{k: v for k, v in item.items() if v is not None})
                for item in raw["required_elements"]
            ],
            preconditions=[
                Check(**{k: v for k, v in item.items() if v is not None})
                for item in raw["preconditions"]
            ],
        )
        meta, body = parse_skill_md(render_skill_md(meta, str(raw["steps"])))
    except (ValueError, KeyError, TypeError) as exc:
        candidate.rejected.append(f"not in form: {exc}")
        return candidate

    source_args = _decode_args(raw.get("source_args"))
    try:
        meta.check_args(source_args)
    except SkillFormatError as exc:
        candidate.rejected.append(f"source_args do not fit the parameters: {exc}")
        return candidate
    literals = sorted(
        {
            str(value)
            for value in source_args.values()
            if not isinstance(value, bool) and names_an_instance(str(value))
        }
        | set(episode_literals(episode))
    )
    candidate.param_slots = {str(item["name"]): item.get("slot") or None for item in raw["params"]}
    uncovered = uncovered_slots(candidate.param_slots, episode)
    leaked = _leaks(body, literals)
    if leaked:
        candidate.rejected.append(
            f"the steps carry literal values of the task: {', '.join(leaked)}"
        )
        return candidate
    candidate.skill = Skill(meta, body)
    candidate.source_args = source_args

    code = raw.get("code")
    if uncovered:
        # A skill that fixes a slot's value would run on a sibling task and do the
        # wrong thing. Such a skill is never given code.
        candidate.code_problems.append(
            "no parameter carries the template's slot "
            + ", ".join(f"{{{{{slot}}}}}" for slot in uncovered)
            + "; every slot must be a parameter"
        )
    if code:
        try:
            check_code(Skill(meta, body, code))
        except SkillFormatError as exc:
            candidate.code_problems.append(str(exc))
        leaked = _leaks(_code_strings(code), literals)
        if leaked:
            candidate.code_problems.append(
                f"the code carries literal values of the task: {', '.join(leaked)}"
            )
        if not candidate.code_problems:
            candidate.code = code
    else:
        candidate.notes.append("the model wrote no code")

    shown = episode.page_text().casefold()
    for item in raw.get("other_args") or []:
        args = _decode_args(item.get("args"))
        reason = _unusable(args, meta, source_args, shown, excluded_texts)
        if reason is None:
            candidate.other_args.append(args)
        else:
            candidate.notes.append(f"other_args {json.dumps(args)} not used: {reason}")
    candidate.other_args = candidate.other_args[:2]
    return candidate


def _unusable(
    args: dict[str, Any],
    meta: SkillMeta,
    source_args: dict[str, Any],
    shown: str,
    excluded_texts: Sequence[str],
) -> str | None:
    """Why a set of other values may not be used for a replay, or None if it may."""
    try:
        meta.check_args(args)
    except SkillFormatError as exc:
        return str(exc)
    if args == source_args:
        return "the same as the episode's values"
    strings = [str(value) for value in args.values() if isinstance(value, str) and value]
    unseen = [value for value in strings if value.casefold() not in shown]
    if unseen:
        return f"not shown on the episode's pages: {', '.join(unseen)}"
    for text in excluded_texts:
        lowered = text.casefold()
        with_digit = [v for v in strings if any(c.isdigit() for c in v) and v.casefold() in lowered]
        if with_digit:
            return f"a held-out task uses {with_digit[0]}"
        if strings and all(value.casefold() in lowered for value in strings):
            return "a held-out task uses the same values"
    return None


def induce_skill(llm: LLMClient, episode: Episode, excluded_texts: Sequence[str] = ()) -> Candidate:
    """Write a skill from a successful episode; one second try if the first is refused."""
    prompt = (
        "The episode follows. Addresses are site-relative; element numbers were removed.\n\n"
        + episode.render(with_template=True)
    )
    raw = ask(llm, INDUCE_SYSTEM, prompt, SAVE_SKILL)
    candidate = check_candidate(raw, episode, excluded_texts)
    candidate.attempts = 1
    problems = candidate.rejected + candidate.code_problems
    if not problems:
        return candidate
    retry = (
        f"{prompt}\n\nYour previous answer was:\n{json.dumps(raw, ensure_ascii=False)}\n\n"
        "It was refused for these reasons:\n"
        + "\n".join(f"- {problem}" for problem in problems)
        + "\n\nCall save_skill again with a corrected skill."
    )
    second = check_candidate(ask(llm, INDUCE_SYSTEM, retry, SAVE_SKILL), episode, excluded_texts)
    second.attempts = 2
    second.notes.append("first attempt refused: " + "; ".join(problems))
    # A second answer that is worse than the first does not replace it.
    if second.skill is None and candidate.skill is not None:
        candidate.attempts = 2
        candidate.notes.append("second attempt refused: " + "; ".join(second.rejected))
        return candidate
    return second


# -- site facts and lessons ------------------------------------------------


@dataclass(frozen=True)
class Note:
    """A site fact or a lesson before it is stored."""

    text: str
    url_pattern: str
    sources: tuple[dict[str, Any], ...]


def _checked_notes(raw: Any, episode: Episode, limit: int) -> tuple[list[Note], list[str]]:
    kept, dropped = [], []
    literals = episode_literals(episode)
    for item in (raw or [])[:limit]:
        text = re.sub(r"\s+", " ", str(item.get("text", ""))).strip()
        pattern = str(item.get("url_pattern", "")).strip()
        try:
            re.compile(pattern)
        except re.error:
            dropped.append(f"{text[:60]!r}: url_pattern {pattern!r} is not a regular expression")
            continue
        if not text or not pattern:
            dropped.append("an empty note")
        elif len(text) > MAX_ITEM_CHARS:
            dropped.append(f"{text[:60]!r}: longer than {MAX_ITEM_CHARS} characters")
        elif _leaks(text, literals):
            dropped.append(f"{text[:60]!r}: carries a literal value of the task")
        else:
            kept.append(Note(text, pattern, (episode.source(),)))
    return kept, dropped


def extract_facts(llm: LLMClient, episode: Episode) -> tuple[list[Note], list[str]]:
    """Site facts from one successful episode, and what was dropped and why."""
    raw = ask(llm, FACTS_SYSTEM, episode.render(), SAVE_FACTS)
    return _checked_notes(raw.get("facts"), episode, limit=4)


def reflect(llm: LLMClient, episode: Episode) -> tuple[list[Note], list[str]]:
    """Lessons from one failed episode. The call sees the trace and that it failed."""
    raw = ask(llm, LESSONS_SYSTEM, episode.render(), SAVE_LESSONS)
    return _checked_notes(raw.get("lessons"), episode, limit=2)


def merge_notes(llm: LLMClient, notes: dict[str, Note]) -> list[tuple[Note, list[str]]]:
    """Merge notes that say the same thing. Returns each kept note with the ids it
    stands for; an id the model lost or used twice keeps its note as it was."""
    if len(notes) < 2:
        return [(note, [key]) for key, note in notes.items()]
    listing = "\n".join(
        f"{key}: {note.text} (pages: {note.url_pattern})" for key, note in notes.items()
    )
    raw = ask(llm, MERGE_SYSTEM, listing, MERGE_ITEMS)
    merged: list[tuple[Note, list[str]]] = []
    used: set[str] = set()
    for item in raw.get("items") or []:
        ids = [key for key in item.get("from") or [] if key in notes and key not in used]
        text = re.sub(r"\s+", " ", str(item.get("text", ""))).strip()
        pattern = str(item.get("url_pattern", "")).strip()
        try:
            re.compile(pattern)
        except re.error:
            continue
        if not ids or not text or not pattern or len(text) > MAX_ITEM_CHARS:
            continue
        used.update(ids)
        if len(ids) == 1:
            # A note that stands for itself stays word for word as it was written.
            merged.append((notes[ids[0]], ids))
            continue
        sources = tuple(source for key in ids for source in notes[key].sources)
        merged.append((Note(text, pattern, sources), ids))
    merged.extend((note, [key]) for key, note in notes.items() if key not in used)
    return merged
