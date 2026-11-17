"""Print a memory build in full, as Markdown.

    uv run python scripts/show_memory.py memory_store/<date>_<name>

Skills with their parameters, the slots they carry and the verdict on their code;
every site fact and lesson with its pattern and sources; and what the build cost.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from browser_agent.memory.pipeline import CANDIDATES, read_log
from browser_agent.memory.store import MemoryStore


def sources(item_source: object) -> str:
    listed = item_source if isinstance(item_source, list) else [item_source]
    tasks = sorted({str(source.get("task_id")) for source in listed if isinstance(source, dict)})
    return ", ".join(tasks)


def build_cost(root: Path, name: str) -> tuple[int, float]:
    spend = root / "results" / "spend.jsonl"
    calls, cost = 0, 0.0
    if spend.exists():
        with spend.open(encoding="utf-8") as handle:
            for line in handle:
                entry = json.loads(line)
                if entry.get("run") == f"memory_build_{name}":
                    calls += 1
                    cost += entry["cost_usd"]
    return calls, cost


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("build", type=Path)
    args = parser.parse_args(argv)
    build: Path = args.build
    store = MemoryStore.open(build)
    provenance = store.provenance()
    log = read_log(build)
    verdicts = {}
    verification = build / "verification.json"
    if verification.exists():
        verdicts = {v["name"]: v for v in json.loads(verification.read_text(encoding="utf-8"))}

    print(f"# Memory build {build.name}\n")
    print(
        f"Model `{provenance.get('model')}`, code {provenance.get('code_commit')}, from runs "
        f"{', '.join(provenance.get('source_runs', []))}.\n"
    )
    calls, cost = build_cost(Path.cwd(), provenance.get("name", ""))
    print(f"Model calls for this build: {calls}, ${cost:.4f}.\n")

    print("## Skills\n")
    print("| Skill | Template | Source task | Parameters (slot) | Code | Verdict |")
    print("|---|---:|---:|---|---|---|")
    for item in store.items("skill"):
        skill = store.skills()[item.id]
        info_path = build / CANDIDATES / item.id / "candidate.json"
        info = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() else {}
        slots = info.get("param_slots", {})
        params = ", ".join(f"{name} ({slots.get(name) or '-'})" for name in skill.meta.params)
        verdict = verdicts.get(item.id, {})
        why = verdict.get("why") or "; ".join(info.get("code_problems") or info.get("notes") or [])
        print(
            f"| {item.id} v{item.version} | {info.get('template_id', '')} | "
            f"{sources(item.source)} | {params or 'none'} | "
            f"{'kept' if skill.code is not None else 'none'} | {why[:260]} |"
        )
    rejected = [event for event in log if event["event"] == "skill_rejected"]
    for event in rejected:
        print(f"\nNo skill for template {event['template']}: {'; '.join(event['why'])[:300]}")
    missing = provenance.get("templates_without_a_successful_episode", [])
    if missing:
        print(f"\nTemplates without a successful learn episode (no skill): {missing}")

    for kind, title in (("site_fact", "Site facts"), ("lesson", "Lessons")):
        items = store.items(kind)
        retired = len(store.items(kind, active_only=False)) - len(items)
        print(f"\n## {title}\n")
        print(f"{len(items)} active, {retired} retired versions.\n")
        for item in items:
            where = f"`{item.url_pattern}` (tasks {sources(item.source)})"
            print(f"- `{item.label}` on {where}: {item.text}")
    store.close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
