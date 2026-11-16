"""Run a set of tasks and write the results.

    uv run python -m browser_agent.eval.runner --config configs/smoke.json

Each run gets its own directory, results/<date>_<name>/, holding the config, one
record per task and a summary. Traces (event logs, network traces) go under traces/,
which git ignores.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from browser_agent.browser import actions
from browser_agent.browser.session import BrowserConfig, BrowserSession, origin_of
from browser_agent.context.observe import PageRenderer, ViewOptions
from browser_agent.eval.webarena import ShoppingAdmin, SiteConfig, load_subset
from browser_agent.harness.events import EventLog
from browser_agent.harness.llm import LLMClient, client_from_env
from browser_agent.harness.loop import AgentLoop, Budgets, LoopConfig
from browser_agent.harness.tools import ToolExecutor

# AGENTS.md: anything larger than a smoke test needs the user's go-ahead.
SMOKE_TASK_LIMIT = 5


class BudgetSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_steps: int = 30
    max_tokens: int = 1_000_000
    max_seconds: float = 900.0
    max_usd: float = 2.0


class Switches(BaseModel):
    """Context and memory components. Every switch is off unless a config turns it on."""

    model_config = ConfigDict(extra="forbid")

    # Observation: show only what can be acted on and what can be read.
    prune_observation: bool = False
    # Observation: count the tail of long runs of rows and options instead of listing it.
    truncate_lists: bool = False
    # Observation: show only what changed while the page stays the same document.
    diff_observation: bool = False
    # Run every tool call of a reply instead of only the first.
    multi_action: bool = False

    def view_options(self) -> ViewOptions:
        return ViewOptions(
            prune=self.prune_observation,
            truncate=self.truncate_lists,
            diff=self.diff_observation,
        )


class RunConfig(BaseModel):
    """An experiment: which tasks, which limits, which switches."""

    model_config = ConfigDict(extra="forbid")

    name: str
    subset: str = "configs/subset.json"
    split: Literal["learn", "test"] | None = None
    task_ids: list[int] | None = None
    limit: int | None = None
    reset: Literal["always", "never"] = "always"
    headless: bool = True
    budgets: BudgetSettings = Field(default_factory=BudgetSettings)
    switches: Switches = Field(default_factory=Switches)


def select_tasks(config: RunConfig, root: Path) -> list[dict[str, Any]]:
    """The subset entries this run covers, in subset order."""
    entries = load_subset(root / config.subset)
    if config.split is not None:
        entries = [entry for entry in entries if entry["split"] == config.split]
    if config.task_ids is not None:
        wanted = set(config.task_ids)
        entries = [entry for entry in entries if entry["task_id"] in wanted]
    if config.limit is not None:
        entries = entries[: config.limit]
    return entries


def new_run_dir(results: Path, name: str, today: str | None = None) -> Path:
    """results/<date>_<name>, with a numeric suffix rather than reusing a directory."""
    today = today or datetime.now().strftime("%Y-%m-%d")
    candidate = results / f"{today}_{name}"
    suffix = 2
    while candidate.exists():
        candidate = results / f"{today}_{name}_{suffix}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


USAGE_KEYS = ("input_tokens", "cached_input_tokens", "cache_write_tokens", "output_tokens")


def cache_hit_rate(usage: dict[str, int]) -> float:
    """Share of the prompt tokens that were read from the provider's cache."""
    prompt = sum(usage.get(key, 0) for key in USAGE_KEYS[:3])
    return usage.get("cached_input_tokens", 0) / prompt if prompt else 0.0


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-task records; means are over all tasks, failed ones included."""
    count = len(records)

    def mean(key: str) -> float:
        return sum(record[key] for record in records) / count if count else 0.0

    usage = {key: sum(r.get("usage", {}).get(key, 0) for r in records) for key in USAGE_KEYS}
    sections: Counter[str] = Counter()
    for record in records:
        sections.update(record.get("sections", {}))
    return {
        "tasks": count,
        "successes": sum(1 for record in records if record["success"]),
        "success_rate": mean("success"),
        "mean_tokens": mean("tokens"),
        "mean_usd": mean("usd"),
        "mean_seconds": mean("seconds"),
        "mean_steps": mean("steps"),
        "total_usd": sum(record["usd"] for record in records),
        "total_tokens": sum(record["tokens"] for record in records),
        "usage": usage,
        "cache_hit_rate": cache_hit_rate(usage),
        # Estimated prompt tokens per task, by section of the prompt.
        "mean_section_tokens": {name: tokens / count for name, tokens in sections.items() if count},
        "finish_reasons": dict(Counter(record["finish_reason"] for record in records)),
    }


def summary_markdown(
    name: str, model: str, summary: dict[str, Any], records: list[dict[str, Any]]
) -> str:
    usage = summary["usage"]
    lines = [
        f"# {name}",
        "",
        f"Model: `{model}`. Tasks: {summary['tasks']}. "
        f"Success: {summary['successes']}/{summary['tasks']} ({summary['success_rate']:.0%}).",
        "",
        "| Mean per task | Value |",
        "|---|---:|",
        f"| Tokens | {summary['mean_tokens']:.0f} |",
        f"| USD | {summary['mean_usd']:.4f} |",
        f"| Seconds | {summary['mean_seconds']:.1f} |",
        f"| Steps | {summary['mean_steps']:.1f} |",
        "",
        f"Total: ${summary['total_usd']:.4f}, {summary['total_tokens']} tokens. "
        f"Finish reasons: {summary['finish_reasons']}.",
        "",
        "## Tokens",
        "",
        f"Input: {usage['input_tokens']} uncached, {usage['cached_input_tokens']} read from "
        f"cache, {usage['cache_write_tokens']} written to cache. "
        f"Output: {usage['output_tokens']}. Cache hit rate: {summary['cache_hit_rate']:.0%}.",
        "",
        "| Prompt section | Mean tokens per task (estimate) | Share |",
        "|---|---:|---:|",
    ]
    section_total = sum(summary["mean_section_tokens"].values()) or 1
    for name, tokens in sorted(summary["mean_section_tokens"].items(), key=lambda item: -item[1]):
        lines.append(f"| {name} | {tokens:.0f} | {tokens / section_total:.0%} |")
    lines += [
        "",
        "## Tasks",
        "",
        "| Task | Template | Split | Success | Tokens | Cached | USD | Seconds | Steps | Finish |",
        "|---:|---:|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for record in records:
        lines.append(
            f"| {record['task_id']} | {record['template_id']} | {record['split']} | "
            f"{'yes' if record['success'] else 'no'} | {record['tokens']} | "
            f"{record.get('cache_hit_rate', 0.0):.0%} | "
            f"{record['usd']:.4f} | {record['seconds']:.1f} | {record['steps']} | "
            f"{record['finish_reason']} |"
        )
    return "\n".join(lines) + "\n"


def _git_commit(root: Path) -> str | None:
    try:
        done = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root, capture_output=True, text=True, timeout=10, check=False,
        )  # fmt: skip
    except OSError:
        return None
    return done.stdout.strip() or None


def run_task(
    entry: dict[str, Any],
    env: ShoppingAdmin,
    browser: BrowserSession,
    llm: LLMClient,
    config: RunConfig,
    run_dir: Path,
) -> dict[str, Any]:
    """Reset, run and score one task; returns its record."""
    task = env.task(entry["task_id"])
    trace_dir = run_dir / "traces" / str(task.task_id)
    trace_dir.mkdir(parents=True)
    reset_seconds = env.reset() if config.reset == "always" else 0.0

    browser.reset_state()
    browser.set_extra_headers(env.site.auth_headers)
    actions.goto(browser, task.start_url)

    events = EventLog(trace_dir / "events.jsonl")
    # One renderer per task: it remembers the last page to diff against.
    renderer = PageRenderer(config.switches.view_options())
    loop = AgentLoop(
        llm=llm.labelled(run=run_dir.name, task_id=task.task_id),
        executor=ToolExecutor(
            browser,
            allowed_origins=[origin_of(env.site.url)],
            render=renderer.render,
            render_section=renderer.section,
        ),
        events=events,
        config=LoopConfig(
            budgets=Budgets(**config.budgets.model_dump()),
            multi_action=config.switches.multi_action,
        ),
    )
    result = loop.run(task.intent)

    response = (
        result.finish.response()
        if result.finish is not None
        else {
            # The evaluator needs a well-formed answer even when the agent gave none.
            "task_type": "RETRIEVE",
            "status": "UNKNOWN_ERROR",
            "retrieved_data": None,
            "error_details": f"no answer: {result.reason}",
        }
    )
    (trace_dir / "agent_response.json").write_text(
        json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    har_path = trace_dir / "network.har"
    assert browser.recorder is not None
    browser.recorder.save(har_path)
    score = env.evaluate(task.task_id, response, har_path)
    (trace_dir / "eval_result.json").write_text(
        json.dumps(score.detail, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "task_id": task.task_id,
        "template_id": task.template_id,
        "split": entry["split"],
        "task_type": entry["task_type"],
        "success": score.success,
        "score": score.score,
        "eval_status": score.status,
        "finish_reason": result.reason,
        "forced": result.forced,
        "answered": result.finish is not None,
        "steps": result.steps,
        "tokens": result.usage.total_tokens,
        "usage": asdict(result.usage),
        "cache_hit_rate": round(cache_hit_rate(asdict(result.usage)), 4),
        "sections": result.sections,
        "usd": result.cost_usd,
        "seconds": round(result.seconds, 2),
        "reset_seconds": round(reset_seconds, 2),
        "error": result.error,
    }


def run(config: RunConfig, root: Path, confirm_paid: bool = False) -> Path:
    """Run every selected task and return the run directory."""
    entries = select_tasks(config, root)
    if not entries:
        raise SystemExit("the config selects no tasks")
    if len(entries) > SMOKE_TASK_LIMIT and not confirm_paid:
        raise SystemExit(
            f"this run has {len(entries)} tasks; runs above {SMOKE_TASK_LIMIT} tasks need "
            "the user's go-ahead and the --confirm-paid flag"
        )
    load_dotenv(root / ".env")
    os.environ["BH_TELEMETRY"] = "0"
    results = root / "results"
    llm = client_from_env(results, parallel_tools=config.switches.multi_action)
    env = ShoppingAdmin(SiteConfig.from_env())
    data_dir = Path(os.environ.get("BROWSER_AGENT_DATA_DIR", "").strip() or root / "data")
    browser_path = os.environ.get("BROWSER_PATH", "").strip()

    run_dir = new_run_dir(results, config.name)
    (run_dir / "config.json").write_text(
        json.dumps(
            {
                "config": config.model_dump(),
                "model": llm.model,
                "pricing_usd_per_mtok": asdict(llm.pricing),
                "site_image": env.site.image,
                "git_commit": _git_commit(root),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    records: list[dict[str, Any]] = []
    session = BrowserSession(
        BrowserConfig(
            data_dir=data_dir,
            browser_path=Path(browser_path) if browser_path else None,
            headless=config.headless,
        )
    )
    with session:
        for entry in entries:
            try:
                record = run_task(entry, env, session, llm, config, run_dir)
            except Exception as exc:
                record = {
                    "task_id": entry["task_id"], "template_id": entry["template_id"],
                    "split": entry["split"], "task_type": entry["task_type"],
                    "success": False, "score": 0.0, "eval_status": "not_scored",
                    "finish_reason": "harness_error", "forced": False, "answered": False,
                    "steps": 0, "tokens": 0, "usage": {}, "usd": 0.0, "seconds": 0.0,
                    "reset_seconds": 0.0, "error": f"{type(exc).__name__}: {exc}",
                }  # fmt: skip
            records.append(record)
            with (run_dir / "records.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(
                f"task {record['task_id']}: {'success' if record['success'] else 'fail'} "
                f"({record['finish_reason']}, {record['steps']} steps, {record['tokens']} tokens, "
                f"${record['usd']:.4f}, {record['seconds']:.0f}s)",
                flush=True,
            )
            if record["finish_reason"] == "spend_cap":
                print("stopping: the BUDGET_USD cap would be exceeded", flush=True)
                break

    summary = summarize(records)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (run_dir / "summary.md").write_text(
        summary_markdown(run_dir.name, llm.model, summary, records), encoding="utf-8"
    )
    llm.ledger.write_summary()
    return run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--confirm-paid",
        action="store_true",
        help=f"allow a run of more than {SMOKE_TASK_LIMIT} tasks (needs the user's go-ahead)",
    )
    args = parser.parse_args(argv)
    config = RunConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
    run_dir = run(config, Path.cwd(), confirm_paid=args.confirm_paid)
    print(f"results: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
