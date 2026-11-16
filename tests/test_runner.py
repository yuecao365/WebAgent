"""Run driver and site control, without Docker, a browser or a model."""

from __future__ import annotations

import json
import subprocess

import pytest
from pydantic import ValidationError

from browser_agent.eval import runner
from browser_agent.eval.runner import RunConfig, new_run_dir, select_tasks, summarize
from browser_agent.eval.webarena import ShoppingAdmin, SiteConfig, SiteError


def write_subset(root, count=8):
    entries = [
        {
            "task_id": 100 + n,
            "template_id": 1 + n // 4,
            "split": "learn" if n % 4 == 0 else "test",
            "task_type": "retrieve",
            "intent": f"intent {n}",
        }
        for n in range(count)
    ]
    (root / "configs").mkdir()
    (root / "configs" / "subset.json").write_text(json.dumps({"tasks": entries}), encoding="utf-8")
    return entries


def test_select_tasks_filters_by_split_ids_and_limit(tmp_path):
    write_subset(tmp_path)

    def ids(**settings):
        return [t["task_id"] for t in select_tasks(RunConfig(name="x", **settings), tmp_path)]

    assert ids() == [100, 101, 102, 103, 104, 105, 106, 107]
    assert ids(split="learn") == [100, 104]
    assert ids(split="test", limit=2) == [101, 102]
    assert ids(task_ids=[107, 101]) == [101, 107]


def test_switches_are_off_by_default_and_unknown_ones_are_rejected():
    config = RunConfig(name="baseline")

    assert not any(config.switches.model_dump().values())
    with pytest.raises(ValidationError):
        RunConfig.model_validate({"name": "x", "switches": {"teleport": True}})
    with pytest.raises(ValidationError):
        RunConfig.model_validate({"name": "x", "budgets": {"max_stepz": 3}})


def test_checked_in_configs_are_valid():
    for path in sorted((runner.Path(__file__).resolve().parents[1] / "configs").glob("*.json")):
        if path.name != "subset.json":
            RunConfig.model_validate_json(path.read_text(encoding="utf-8"))


def test_a_run_directory_is_never_reused(tmp_path):
    first = new_run_dir(tmp_path, "smoke", today="2026-11-16")
    second = new_run_dir(tmp_path, "smoke", today="2026-11-16")
    third = new_run_dir(tmp_path, "smoke", today="2026-11-16")

    assert [p.name for p in (first, second, third)] == [
        "2026-11-16_smoke",
        "2026-11-16_smoke_2",
        "2026-11-16_smoke_3",
    ]
    assert all(p.is_dir() for p in (first, second, third))


def test_runs_above_the_smoke_size_need_confirmation(tmp_path):
    write_subset(tmp_path, count=6)

    with pytest.raises(SystemExit) as stopped:
        runner.run(RunConfig(name="big"), tmp_path)

    assert "6 tasks" in str(stopped.value)
    assert "--confirm-paid" in str(stopped.value)
    # Refused before anything was created or spent.
    assert not (tmp_path / "results").exists()


def test_summary_counts_failures_in_the_means():
    done = {"success": True, "tokens": 1000, "usd": 0.10, "seconds": 20.0, "steps": 4}
    cut = {"success": False, "tokens": 3000, "usd": 0.30, "seconds": 60.0, "steps": 8}
    records = [
        {**done, "finish_reason": "finished"},
        {**cut, "finish_reason": "budget_steps"},
    ]

    summary = summarize(records)

    assert summary["tasks"] == 2
    assert summary["successes"] == 1
    assert summary["success_rate"] == 0.5
    assert summary["mean_tokens"] == 2000
    assert summary["mean_usd"] == pytest.approx(0.20)
    assert summary["mean_seconds"] == 40.0
    assert summary["mean_steps"] == 6
    assert summary["total_usd"] == pytest.approx(0.40)
    assert summary["finish_reasons"] == {"finished": 1, "budget_steps": 1}


def test_summary_reports_the_token_split_cache_rate_and_sections():
    base = {"success": True, "tokens": 0, "usd": 0.0, "seconds": 1.0, "steps": 1}
    records = [
        {
            **base,
            "finish_reason": "finished",
            "usage": {"input_tokens": 100, "cached_input_tokens": 700, "cache_write_tokens": 200},
            "sections": {"system": 300, "history": 500, "observation": 200},
        },
        {
            **base,
            "finish_reason": "finished",
            "usage": {"input_tokens": 900, "cached_input_tokens": 100, "output_tokens": 40},
            "sections": {"system": 300, "history": 100, "observation": 600},
        },
    ]

    summary = summarize(records)

    assert summary["usage"] == {
        "input_tokens": 1000,
        "cached_input_tokens": 800,
        "cache_write_tokens": 200,
        "output_tokens": 40,
    }
    assert summary["cache_hit_rate"] == pytest.approx(0.4)
    assert summary["mean_section_tokens"] == {"system": 300, "history": 300, "observation": 400}
    assert runner.cache_hit_rate(records[0]["usage"]) == pytest.approx(0.7)
    text = runner.summary_markdown("run", "m", summary, [])
    assert "Cache hit rate: 40%." in text
    assert "| observation | 400 | 40% |" in text


def test_summary_of_nothing():
    assert summarize([])["success_rate"] == 0.0
    assert summarize([])["cache_hit_rate"] == 0.0


def test_summary_markdown_has_a_row_per_task():
    record = {
        "task_id": 288, "template_id": 234, "split": "learn", "success": True, "tokens": 1234,
        "usd": 0.0123, "seconds": 45.6, "steps": 7, "finish_reason": "finished",
    }  # fmt: skip

    text = runner.summary_markdown("2026-11-16_smoke", "some-model", summarize([record]), [record])

    assert "Success: 1/1 (100%)" in text
    assert "| 288 | 234 | learn | yes | 1234 | 0% | 0.0123 | 45.6 | 7 | finished |" in text


# -- site control ---------------------------------------------------------------


class Docker:
    def __init__(self, run_fails=False):
        self.commands = []
        self.run_fails = run_fails

    def __call__(self, args):
        self.commands.append(list(args))
        failed = self.run_fails and args[1] == "run"
        return subprocess.CompletedProcess(
            args, 1 if failed else 0, "", "port is already allocated"
        )


def test_reset_replaces_the_container(monkeypatch):
    docker = Docker()
    site = SiteConfig(url="http://localhost:7780", env_ctrl_url="http://localhost:7781")
    env = ShoppingAdmin(site, run_command=docker)
    waited = []
    monkeypatch.setattr(env, "wait_ready", lambda timeout: waited.append(timeout))

    seconds = env.reset()

    assert docker.commands[0] == ["docker", "rm", "-f", "webarena-verified-shopping_admin"]
    run = docker.commands[1]
    assert run[:3] == ["docker", "run", "-d"]
    # Published on the loopback interface only.
    assert "127.0.0.1:7780:80" in run
    assert "127.0.0.1:7781:8877" in run
    assert "WA_ENV_CTRL_EXTERNAL_SITE_URL=http://localhost:7780" in run
    assert run[-1] == "am1n3e/webarena-verified-shopping_admin:0.1.0"
    assert len(waited) == 1
    assert seconds >= 0


def test_reset_reports_a_failed_start(monkeypatch):
    env = ShoppingAdmin(run_command=Docker(run_fails=True))
    monkeypatch.setattr(env, "wait_ready", lambda timeout: None)

    with pytest.raises(SiteError, match="port is already allocated"):
        env.reset()


def test_wait_ready_needs_two_good_checks_in_a_row(monkeypatch):
    env = ShoppingAdmin(sleep=lambda seconds: None)
    # Not healthy; good; sign-in fails and the count starts over; good; good.
    health = iter([False, True, True, True, True])
    sign_in = iter([True, False, True, True])
    monkeypatch.setattr(env, "_healthy", lambda: next(health))
    monkeypatch.setattr(env, "_signs_in", lambda: next(sign_in))

    env.wait_ready(timeout=30)

    assert next(health, "used up") == "used up"


def test_site_config_from_env(monkeypatch):
    monkeypatch.setenv("WEBARENA_SHOPPING_ADMIN_URL", "http://localhost:8080/")
    monkeypatch.delenv("WEBARENA_SHOPPING_ADMIN_ENV_CTRL_URL", raising=False)

    site = SiteConfig.from_env()

    assert site.admin_url == "http://localhost:8080/admin"
    assert site.env_ctrl_url == "http://localhost:7781"
    assert site.auth_headers == {"X-M2-Admin-Auto-Login": "admin:admin1234"}


def test_tasks_are_rendered_for_the_local_site():
    task = ShoppingAdmin(SiteConfig(url="http://localhost:7780")).task(288)

    assert task.template_id == 234
    assert task.start_url == "http://localhost:7780/admin"
    assert "most cancellations" in task.intent
