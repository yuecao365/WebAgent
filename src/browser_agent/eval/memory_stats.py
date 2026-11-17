"""What long-term memory did in a run, counted from the event logs.

For skills: how many tasks loaded or ran one, how often the gate passed, why it
rejected, how often code ran through, how often the model was handed the steps, and
how those tasks ended. A "wrong replay" candidate is a task in which skill code ran
through every check and the task still failed; whether the fault lies in the skill's
part or after it has to be read from the trace.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from browser_agent.harness.events import read_events


def _success(events: list[dict[str, Any]], recorded: bool | None) -> bool:
    scored = next((event for event in events if event["type"] == "task_scored"), None)
    return bool(scored["success"]) if scored is not None else bool(recorded)


def run_memory_stats(run_dir: Path) -> dict[str, Any]:
    """Counts over every task of a run that has an event log."""
    records = {}
    records_path = run_dir / "records.jsonl"
    if records_path.exists():
        with records_path.open(encoding="utf-8") as handle:
            records = {str(r["task_id"]): r for r in map(json.loads, filter(str.strip, handle))}
    stats: dict[str, Any] = {
        "tasks": 0,
        "successes": 0,
        "tasks_loading_a_skill": 0,
        "tasks_calling_run_skill": 0,
        "tasks_shown_a_lesson": 0,
        "skill_loads": 0,
        "gate_passed": 0,
        "gate_rejected": 0,
        "rejections_by_check": Counter(),
        "code_ran_through": 0,
        "code_stopped_at_a_step": 0,
        "handed_steps_to_model": 0,
        "lessons_shown": 0,
        "by_skill": {},
        "per_task": [],
    }
    logs = sorted((run_dir / "traces").glob("*/events.jsonl"), key=lambda p: int(p.parent.name))
    for log in logs:
        events = read_events(log)
        task_id = log.parent.name
        success = _success(events, records.get(task_id, {}).get("success"))
        task: dict[str, Any] = {
            "task_id": int(task_id),
            "success": success,
            "loaded": [],
            "gate": [],
            "code": [],
            "lessons": [],
        }
        for event in events:
            kind = event["type"]
            skill = event.get("skill")
            if kind == "skill_loaded":
                task["loaded"].append(skill)
            elif kind == "gate_passed":
                task["gate"].append((skill, "passed"))
            elif kind == "gate_rejected":
                task["gate"].append((skill, event.get("check", "")))
                stats["rejections_by_check"][event.get("check", "")] += 1
            elif kind == "skill_code_run":
                task["code"].append((skill, bool(event.get("ok"))))
            elif kind == "skill_guided":
                stats["handed_steps_to_model"] += 1
            elif kind == "lesson_shown":
                task["lessons"].append(event.get("lesson"))
            if skill and kind in ("skill_loaded", "gate_passed", "gate_rejected", "skill_code_run"):
                row = stats["by_skill"].setdefault(
                    skill, {"loaded": 0, "gate_passed": 0, "gate_rejected": 0, "ran_through": 0}
                )
                if kind == "skill_code_run":
                    row["ran_through"] += bool(event.get("ok"))
                else:
                    row[{"skill_loaded": "loaded"}.get(kind, kind)] += 1
        stats["tasks"] += 1
        stats["successes"] += success
        stats["tasks_loading_a_skill"] += bool(task["loaded"])
        stats["tasks_calling_run_skill"] += bool(task["gate"])
        stats["tasks_shown_a_lesson"] += bool(task["lessons"])
        stats["skill_loads"] += len(task["loaded"])
        stats["gate_passed"] += sum(1 for _, outcome in task["gate"] if outcome == "passed")
        stats["gate_rejected"] += sum(1 for _, outcome in task["gate"] if outcome != "passed")
        stats["code_ran_through"] += sum(1 for _, ok in task["code"] if ok)
        stats["code_stopped_at_a_step"] += sum(1 for _, ok in task["code"] if not ok)
        stats["lessons_shown"] += len(task["lessons"])
        # Code ran through every check, and the task failed all the same.
        task["wrong_replay_candidate"] = not success and any(ok for _, ok in task["code"])
        stats["per_task"].append(task)
    stats["rejections_by_check"] = dict(stats["rejections_by_check"])
    return stats


def memory_markdown(stats: dict[str, Any]) -> str:
    """The counts as text, with one line per task that touched memory."""
    lines = [
        f"Tasks: {stats['tasks']}, successful {stats['successes']}.",
        "",
        "| What | Count |",
        "|---|---:|",
        f"| Tasks that called load_skill | {stats['tasks_loading_a_skill']} |",
        f"| Tasks that called run_skill | {stats['tasks_calling_run_skill']} |",
        f"| load_skill calls | {stats['skill_loads']} |",
        f"| run_skill: gate passed | {stats['gate_passed']} |",
        f"| run_skill: gate rejected | {stats['gate_rejected']} |",
        f"| Code ran through every check | {stats['code_ran_through']} |",
        f"| Code stopped at a step | {stats['code_stopped_at_a_step']} |",
        f"| Steps handed to the model (guided) | {stats['handed_steps_to_model']} |",
        f"| Tasks shown a lesson | {stats['tasks_shown_a_lesson']} |",
        "",
    ]
    if stats["rejections_by_check"]:
        listed = ", ".join(f"{check}: {n}" for check, n in stats["rejections_by_check"].items())
        lines += [f"Gate rejections by check: {listed}.", ""]
    lines += [
        "| Task | Success | Loaded | run_skill | Code | Lessons |",
        "|---:|---|---|---|---|---:|",
    ]
    for task in stats["per_task"]:
        if not (task["loaded"] or task["gate"] or task["lessons"]):
            continue
        gate = "; ".join(f"{skill}: {outcome}" for skill, outcome in task["gate"])
        code = "; ".join("ran through" if ok else "stopped" for _, ok in task["code"])
        lines.append(
            f"| {task['task_id']} | {'yes' if task['success'] else 'no'} | "
            f"{', '.join(task['loaded'])} | {gate} | {code} | {len(task['lessons'])} |"
        )
    wrong = [task["task_id"] for task in stats["per_task"] if task["wrong_replay_candidate"]]
    lines += ["", f"Tasks where code ran through and the task failed: {wrong or 'none'}."]
    return "\n".join(lines) + "\n"
