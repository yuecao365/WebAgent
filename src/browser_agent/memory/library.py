"""A memory build as a run sees it: read-only, and only the parts switched on.

Three switches, each off unless a run config turns it on:

- skills: the skills are listed in the stable prefix of the prompt, and the tools
  load_skill and run_skill exist;
- site_facts: the facts are listed in the stable prefix, up to a cap;
- lessons: a lesson is shown in the tail of the prompt while the page's address
  matches its url_pattern.

The prefix is the same for every step of every task of a run, so the prompt cache
keeps working with memory on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from browser_agent.memory.skill import Skill
from browser_agent.memory.store import Item, MemoryStore

# About 800 tokens of site facts at four characters per token.
MAX_FACT_CHARS = 3200
# A page can match several lessons; more than a few would bury the page.
MAX_LESSONS_SHOWN = 3

PREFIX_HEAD = (
    "Notes from earlier work on this site. They were written from other tasks and can be "
    "wrong or not fit this one; what the page shows decides."
)
SKILLS_HEAD = (
    "Skills: procedures that worked on an earlier task. load_skill(name) shows a skill's "
    "parameters and steps. run_skill(name, args) runs the skill's verified code if it has "
    "any and the page fits; otherwise it returns the steps for you to follow yourself. A "
    "skill never finishes the task: check the result and call finish yourself."
)
FACTS_HEAD = "Site facts:"
LESSONS_HEAD = "Lessons from earlier failed attempts on pages like this one:"


@dataclass(frozen=True)
class Memory:
    """What of a build a run uses."""

    build: str
    skills: dict[str, Skill] = field(default_factory=dict)
    site_facts: tuple[Item, ...] = ()
    lessons: tuple[Item, ...] = ()

    def prefix(self) -> str | None:
        """The stable message in front of the task, or None when there is nothing to say."""
        parts = []
        if self.skills:
            lines = [SKILLS_HEAD]
            for skill in self.skills.values():
                code = "has code" if skill.code is not None else "steps only"
                # The parameter names are listed: without them the model called
                # run_skill with none or with guessed names and lost a step to the error.
                params = ", ".join(skill.meta.params) or "none"
                lines.append(
                    f"- {skill.meta.name}: {skill.meta.description} "
                    f"(starts on {skill.meta.url_pattern}; parameters: {params}; {code})"
                )
            parts.append("\n".join(lines))
        if self.site_facts:
            lines = [FACTS_HEAD]
            lines += [f"- {fact.text} (pages {fact.url_pattern})" for fact in self.site_facts]
            parts.append("\n".join(lines))
        return "\n\n".join([PREFIX_HEAD, *parts]) if parts else None

    def lessons_at(self, site_path: str) -> list[Item]:
        """The lessons whose url_pattern matches this page, at most a few."""
        matching = [lesson for lesson in self.lessons if re.search(lesson.url_pattern, site_path)]
        return matching[:MAX_LESSONS_SHOWN]

    def versions(self) -> dict[str, list[str]]:
        """Every item a run can see, with its version, for the run's record."""
        return {
            "skills": [f"{name}@v{skill.meta.version}" for name, skill in self.skills.items()],
            "site_facts": [fact.label for fact in self.site_facts],
            "lessons": [lesson.label for lesson in self.lessons],
        }


def capped_facts(facts: list[Item], max_chars: int = MAX_FACT_CHARS) -> tuple[Item, ...]:
    """The facts that fit under the cap: those seen in most episodes first.

    The order is fixed by the build (number of sources, then id), never by the task,
    so the prefix is the same for every task.
    """
    ranked = sorted(facts, key=lambda fact: (-len(fact.source or []), fact.id))
    kept, used = [], 0
    for fact in ranked:
        cost = len(fact.text) + len(fact.url_pattern) + 12
        if used + cost > max_chars:
            continue
        kept.append(fact)
        used += cost
    return tuple(sorted(kept, key=lambda fact: fact.id))


def load_memory(root: Path, build: str, skills: bool, site_facts: bool, lessons: bool) -> Memory:
    """Open a build read-only and take from it what the switches allow."""
    store = MemoryStore.open(root / "memory_store" / build, read_only=True)
    try:
        return Memory(
            build=build,
            skills=store.skills() if skills else {},
            site_facts=capped_facts(store.items("site_fact")) if site_facts else (),
            lessons=tuple(store.items("lesson")) if lessons else (),
        )
    finally:
        store.close()
