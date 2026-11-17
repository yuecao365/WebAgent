"""The memory build: from the traces of learn runs to a build directory.

    uv run python scripts/build_memory.py --config configs/memory_learn_v1.json

Stage "induce" (this module) makes the model calls and stores what they return:
skills as guidance (SKILL.md only), candidate code beside them, site facts and
lessons. Stage "verify" (verify.py) replays the candidate code on the site and gives
a skill its code only if every replay passes.

Everything that happened is appended to build_log.jsonl in the build directory:
which episode each item came from, what was refused and why.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from browser_agent.harness.llm import LLMClient
from browser_agent.memory.build import (
    BuildError,
    Candidate,
    Note,
    extract_facts,
    induce_skill,
    merge_notes,
    reflect,
)
from browser_agent.memory.episodes import Episode, failures, load_episodes, shortest_successes
from browser_agent.memory.store import Kind, MemoryStore

CANDIDATES = "candidates"
LOG_FILE = "build_log.jsonl"


class BuildConfig(BaseModel):
    """What a memory build is made from."""

    model_config = ConfigDict(extra="forbid")

    name: str
    # Run directories under results/ whose traces are read.
    runs: list[str]
    subset: str = "configs/subset.json"
    # Memory is built from the learn tasks and from nothing else.
    split: Literal["learn"] = "learn"
    # Empty: LLM_MODEL from .env. Another model needs its prices here too.
    model: str | None = None
    price_input_per_mtok: float | None = None
    price_output_per_mtok: float | None = None
    reasoning_effort: str = "medium"
    max_output_tokens: int = 12_000


def build_dir(root: Path, name: str, today: str | None = None) -> Path:
    today = today or datetime.now().strftime("%Y-%m-%d")
    return root / "memory_store" / f"{today}_{name}"


def git_commit(root: Path) -> str | None:
    try:
        done = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root, capture_output=True, text=True, timeout=10, check=False,
        )  # fmt: skip
    except OSError:
        return None
    return done.stdout.strip() or None


class BuildLog:
    """Appends what the build did to build_log.jsonl and echoes it."""

    def __init__(self, path: Path, echo: Callable[[str], None] = print) -> None:
        self._path = path
        self._echo = echo

    def add(self, event: str, **details: Any) -> None:
        record = {"ts": datetime.now().isoformat(timespec="seconds"), "event": event, **details}
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        shown = json.dumps(details, ensure_ascii=False)
        self._echo(f"{event}: {shown[:300]}")


def read_log(build: Path) -> list[dict[str, Any]]:
    with (build / LOG_FILE).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def learn_entries(root: Path, config: BuildConfig) -> tuple[list[dict], list[str]]:
    """The learn tasks, and the texts of all other tasks (never to be replayed on)."""
    subset = json.loads((root / config.subset).read_text(encoding="utf-8"))
    tasks = subset["tasks"] if isinstance(subset, dict) else subset
    templates = {
        int(item["template_id"]): str(item.get("intent_template", ""))
        for item in (subset.get("templates", []) if isinstance(subset, dict) else [])
    }
    # Only learn tasks get their template attached: it is dataset metadata, and the
    # build may use that of the tasks it learns from, not of the held-out ones.
    learn = [
        {**entry, "intent_template": templates.get(int(entry["template_id"]), "")}
        for entry in tasks
        if entry["split"] == config.split
    ]
    held_out = [str(entry.get("intent", "")) for entry in tasks if entry["split"] != config.split]
    return learn, held_out


def save_candidate(build: Path, candidate: Candidate) -> None:
    """Keep what induction produced beside the store; runs never read this folder."""
    name = candidate.skill.name if candidate.skill else f"template-{candidate.template_id}"
    folder = build / CANDIDATES / name
    folder.mkdir(parents=True, exist_ok=False)
    if candidate.code is not None:
        (folder / "skill.py").write_text(candidate.code, encoding="utf-8", newline="\n")
    (folder / "candidate.json").write_text(
        json.dumps(
            {
                "template_id": candidate.template_id,
                "source": candidate.source,
                "has_skill": candidate.skill is not None,
                "has_code": candidate.code is not None,
                "source_args": candidate.source_args,
                "param_slots": candidate.param_slots,
                "other_args": candidate.other_args,
                "rejected": candidate.rejected,
                "code_problems": candidate.code_problems,
                "notes": candidate.notes,
                "attempts": candidate.attempts,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _store_notes(
    store: MemoryStore,
    llm: LLMClient,
    kind: Kind,
    prefix: str,
    raw: list[Note],
    log: BuildLog,
) -> None:
    """Store notes as written, then merge the ones that repeat into new versions."""
    notes: dict[str, Note] = {}
    for number, note in enumerate(raw, start=1):
        item_id = f"{prefix}-{number:03d}"
        store.add(kind, item_id, note.text, note.url_pattern, list(note.sources))
        notes[item_id] = note
    if len(notes) < 2:
        return
    try:
        merged = merge_notes(llm.labelled(task_id=f"merge-{prefix}"), notes)
    except BuildError as exc:
        log.add("merge_failed", kind=kind, error=str(exc))
        return
    for note, ids in merged:
        if len(ids) == 1:
            continue
        keep, others = ids[0], ids[1:]
        store.add(
            kind, keep, note.text, note.url_pattern, list(note.sources),
            note=f"merged from {', '.join(ids)}",
        )  # fmt: skip
        for other in others:
            store.retire(kind, other, f"merged into {keep}")
        log.add("merged", kind=kind, into=keep, ids=ids, text=note.text)


def induce(config: BuildConfig, root: Path, llm: LLMClient, build: Path) -> MemoryStore:
    """Stage one: read the learn episodes and store what the model makes of them."""
    learn, held_out = learn_entries(root, config)
    episodes = load_episodes(root / "results", config.runs, learn)
    sources = shortest_successes(episodes)
    failed = failures(episodes)
    store = MemoryStore.create(
        build,
        {
            "name": config.name,
            "config": config.model_dump(),
            "model": llm.model,
            "code_commit": git_commit(root),
            "source_runs": config.runs,
            "learn_tasks": sorted(int(entry["task_id"]) for entry in learn),
            "skill_and_fact_sources": [episode.source() for episode in sources.values()],
            "lesson_sources": [episode.source() for episode in failed],
            "templates_without_a_successful_episode": sorted(
                {int(entry["template_id"]) for entry in learn} - set(sources)
            ),
        },
    )
    log = BuildLog(build / LOG_FILE)
    log.add(
        "sources",
        episodes=len(episodes),
        skill_sources={t: e.key for t, e in sources.items()},
        failed=[e.key for e in failed],
    )

    for template_id, episode in sources.items():
        call = llm.labelled(task_id=f"induce-{template_id}")
        try:
            candidate = induce_skill(call, episode, held_out)
        except BuildError as exc:
            log.add("skill_rejected", template=template_id, source=episode.key, why=[str(exc)])
            continue
        if candidate.skill is not None and candidate.skill.name in store.skills():
            candidate.rejected.append(f"a skill named {candidate.skill.name} already exists")
            candidate.skill = None
        if candidate.skill is None:
            log.add(
                "skill_rejected", template=template_id, source=episode.key, why=candidate.rejected
            )
            continue
        save_candidate(build, candidate)
        store.add_skill(candidate.skill, episode.source(), note="guidance; code not verified")
        log.add(
            "skill_candidate",
            template=template_id,
            source=episode.key,
            name=candidate.skill.name,
            params=list(candidate.skill.meta.params),
            slots=episode.value_slots(),
            param_slots=candidate.param_slots,
            code=candidate.code is not None,
            code_problems=candidate.code_problems,
            other_args=candidate.other_args,
            notes=candidate.notes,
            attempts=candidate.attempts,
        )

    facts: list[Note] = []
    for template_id, episode in sources.items():
        try:
            kept, dropped = extract_facts(llm.labelled(task_id=f"facts-{template_id}"), episode)
        except BuildError as exc:
            log.add("facts_failed", source=episode.key, error=str(exc))
            continue
        facts += kept
        log.add("facts", source=episode.key, kept=[n.text for n in kept], dropped=dropped)
    _store_notes(store, llm, "site_fact", "fact", facts, log)

    lessons: list[Note] = []
    for episode in failed:
        label = f"reflect-{episode.run.split('_', 1)[-1]}-{episode.task_id}"
        try:
            kept, dropped = reflect(llm.labelled(task_id=label), episode)
        except BuildError as exc:
            log.add("reflection_failed", source=episode.key, error=str(exc))
            continue
        lessons += kept
        log.add("lessons", source=episode.key, kept=[n.text for n in kept], dropped=dropped)
    _store_notes(store, llm, "lesson", "lesson", lessons, log)

    store.write_manifest()
    log.add(
        "induced",
        skills=len(store.items("skill")),
        site_facts=len(store.items("site_fact")),
        lessons=len(store.items("lesson")),
    )
    return store


def episode_for(root: Path, config: BuildConfig, source: dict[str, Any]) -> Episode:
    """Load again the episode an item came from."""
    learn, _ = learn_entries(root, config)
    episodes = load_episodes(root / "results", [source["run"]], learn)
    return next(episode for episode in episodes if episode.task_id == source["task_id"])
