"""Run driver and site control, without Docker, a browser or a model."""

from __future__ import annotations

import json
import subprocess

import pytest
from pydantic import ValidationError

from browser_agent.browser.session import BrowserError
from browser_agent.eval import runner
from browser_agent.eval.fallbacks import TaskLog, build_ledger
from browser_agent.eval.runner import RunConfig, new_run_dir, select_tasks, summarize
from browser_agent.eval.webarena import ShoppingAdmin, SiteConfig, SiteError
from browser_agent.harness.events import LOG_VERSION, EventLog, read_events
from browser_agent.memory.pipeline import BuildConfig

from fakes import FINISH_OK, FakeSession, FakeSite, call, make_client, reply


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


def test_only_the_measured_switches_are_on_by_default_and_unknown_ones_are_rejected():
    config = RunConfig(name="baseline")

    # Pruning and truncation were chosen by the learn-task arms; the rest stays off.
    on = {name for name, value in config.switches.model_dump().items() if value}
    assert on == {"prune_observation", "truncate_lists"}
    everything_off = RunConfig.model_validate(
        {"name": "x", "switches": {"prune_observation": False, "truncate_lists": False}}
    )
    assert not any(everything_off.switches.model_dump().values())
    with pytest.raises(ValidationError):
        RunConfig.model_validate({"name": "x", "switches": {"teleport": True}})
    with pytest.raises(ValidationError):
        RunConfig.model_validate({"name": "x", "budgets": {"max_stepz": 3}})


def test_switches_select_the_observation_components():
    config = RunConfig.model_validate(
        {"name": "x", "switches": {"prune_observation": True, "truncate_lists": True}}
    )

    options = config.switches.view_options()

    assert (options.prune, options.truncate, options.diff) == (True, True, False)
    assert not config.switches.multi_action


def test_a_config_can_pick_the_api_and_the_reasoning_effort(tmp_path, monkeypatch):
    write_subset(tmp_path, count=1)
    asked = {}

    def fake_client(results_dir, **kwargs):
        asked.update(kwargs)
        raise SystemExit("stop before any call")

    monkeypatch.setattr(runner, "client_from_env", fake_client)
    monkeypatch.setattr(runner, "preflight", lambda env: None)
    config = RunConfig(name="x", api="responses", reasoning_effort="low")

    with pytest.raises(SystemExit, match="stop before any call"):
        runner.run(config, tmp_path)

    assert (asked["api"], asked["effort"]) == ("responses", "low")
    with pytest.raises(ValidationError):
        RunConfig(name="x", api="assistants")
    # Left empty, .env decides.
    assert (RunConfig(name="x").api, RunConfig(name="x").reasoning_effort) == (None, None)


def test_checked_in_configs_are_valid():
    for path in sorted((runner.Path(__file__).resolve().parents[1] / "configs").glob("*.json")):
        text = path.read_text(encoding="utf-8")
        if path.name.startswith("memory_"):
            BuildConfig.model_validate_json(text)
        elif path.name not in ("subset.json", "probe.json"):
            RunConfig.model_validate_json(text)


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


# -- resets only when the site may be dirty ---------------------------------------


def entry(task_id, state_changing):
    return {"task_id": task_id, "state_changing": state_changing}


def test_read_only_tasks_are_ordered_first_keeping_their_order():
    entries = [entry(1, True), entry(2, False), entry(3, True), entry(4, False), entry(5, False)]

    assert [e["task_id"] for e in runner.order_tasks(entries)] == [2, 4, 5, 1, 3]
    # A task of unknown kind is treated as state-changing.
    assert [e["task_id"] for e in runner.order_tasks([{"task_id": 9}, entry(2, False)])] == [2, 9]


def simulate(scheduler, tasks):
    """Run (state_changing, wrote, crashed) tasks; return which ones were reset before."""
    resets = []
    for state_changing, wrote, crashed in tasks:
        reset = scheduler.needs_reset()
        if reset:
            scheduler.did_reset()
        resets.append(reset)
        scheduler.task_started()
        if not crashed:
            scheduler.task_ended(state_changing, wrote=wrote)
    return resets


READ, WRITE = (False, False, False), (True, False, False)


def test_a_run_starts_with_a_reset_and_read_only_tasks_need_no_more():
    assert simulate(runner.ResetScheduler(), [READ, READ, READ]) == [True, False, False]


def test_every_state_changing_task_is_followed_by_a_reset_whatever_its_outcome():
    scheduler = runner.ResetScheduler()

    resets = simulate(scheduler, [READ, WRITE, WRITE, READ, READ])

    assert resets == [True, False, True, True, False]
    assert scheduler.resets == 3


def test_a_read_only_task_that_wrote_or_crashed_leaves_the_site_dirty():
    wrote, crashed = (False, True, False), (False, False, True)

    assert simulate(runner.ResetScheduler(), [READ, wrote, READ, READ]) == [
        True, False, True, False,
    ]  # fmt: skip
    assert simulate(runner.ResetScheduler(), [READ, crashed, READ]) == [True, False, True]


def test_reset_policies_always_and_never():
    assert simulate(runner.ResetScheduler("always"), [READ, READ]) == [True, True]
    assert simulate(runner.ResetScheduler("never"), [WRITE, WRITE]) == [False, False]


def test_planned_resets_for_the_checked_in_subset():
    root = runner.Path(__file__).resolve().parents[1]
    everything = select_tasks(RunConfig(name="x"), root)
    learn = select_tasks(RunConfig(name="x", split="learn"), root)

    assert len(everything) == 60
    # 36 read-only tasks first, behind one reset; then one reset between the 24 others.
    assert [e["state_changing"] for e in everything] == [False] * 36 + [True] * 24
    assert runner.planned_resets(everything) == 24
    assert runner.planned_resets(everything, "always") == 60
    assert (len(learn), runner.planned_resets(learn)) == (15, 6)


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
        "reasoning_tokens": 0,
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


def test_reset_saves_the_grid_state_and_restore_puts_it_back(monkeypatch):
    docker = Docker()
    env = ShoppingAdmin(run_command=docker)
    monkeypatch.setattr(env, "wait_ready", lambda timeout: None)

    env.reset()
    env.restore_ui_state()

    saved, restored = docker.commands[2], docker.commands[3]
    assert saved[:5] == ["docker", "exec", "webarena-verified-shopping_admin", "bash", "-c"]
    assert saved[5].startswith("mysqldump ")
    assert " ui_bookmark > " in saved[5]
    assert restored[5].startswith("mysql ")
    assert restored[5].endswith(saved[5].split(" > ")[1])


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


def test_summary_markdown_ends_with_the_fallback_ledger():
    record = {
        "task_id": 288, "template_id": 234, "split": "learn", "success": True, "tokens": 1234,
        "usd": 0.0123, "seconds": 45.6, "steps": 7, "finish_reason": "finished",
    }  # fmt: skip
    log = EventLog()
    log.append("task_start", goal="g", log_version=2)
    log.append("nudge", step=1, detail="no tool call")
    log.append("task_end", reason="finished", response={"status": "SUCCESS"})
    log.append("task_scored", success=True)
    summary = summarize([record])
    summary["fallbacks"] = build_ledger([TaskLog(288, log.events)])

    text = runner.summary_markdown("2026-11-16_smoke", "some-model", summary, [record])

    assert "## Fallbacks" in text
    assert "| Reply without a tool call, nudged | 1 | 1 | 0/1 | 1/1 |" in text
    assert "a correlation, not a rescue rate" in text


def test_the_site_is_asked_once_whether_it_answers(monkeypatch):
    env = ShoppingAdmin(
        SiteConfig(url="http://localhost:7780", env_ctrl_url="http://localhost:7781")
    )
    monkeypatch.setattr(env, "_healthy", lambda: False)
    monkeypatch.setattr(env, "_signs_in", lambda: False)

    problems = env.not_answering()

    assert len(problems) == 2
    assert "http://localhost:7781" in problems[0]
    assert "http://localhost:7780/admin" in problems[1]
    monkeypatch.setattr(env, "_healthy", lambda: True)
    monkeypatch.setattr(env, "_signs_in", lambda: True)
    assert env.not_answering() == []


@pytest.mark.parametrize("value", [None, "", "1", "true"])
def test_a_run_refuses_to_start_unless_telemetry_is_off(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("BH_TELEMETRY", raising=False)
    else:
        monkeypatch.setenv("BH_TELEMETRY", value)

    with pytest.raises(SystemExit, match="BH_TELEMETRY is not 0"):
        runner.preflight(FakeSite())


def test_a_run_refuses_to_start_when_the_site_does_not_answer(monkeypatch):
    monkeypatch.setenv("BH_TELEMETRY", "0")
    site = FakeSite()
    runner.preflight(site)  # up: no objection

    site.answering = ["the control service of shop does not answer at http://localhost:7781"]

    with pytest.raises(SystemExit, match="not starting the run: the control service"):
        runner.preflight(site)


def test_a_refused_run_leaves_nothing_behind(tmp_path, monkeypatch):
    write_subset(tmp_path, count=1)
    monkeypatch.setenv("BH_TELEMETRY", "1")
    monkeypatch.setattr(runner, "ShoppingAdmin", lambda site: FakeSite())

    with pytest.raises(SystemExit, match="not starting the run"):
        runner.run(RunConfig(name="x"), tmp_path)

    assert not (tmp_path / "results").exists()


def run_tasks(tmp_path, monkeypatch, session, replies, count):
    """runner.run on some tasks, with the site, the browser and the model faked."""
    write_subset(tmp_path, count=count)
    site = FakeSite()
    llm, provider, _, _ = make_client(tmp_path, replies)
    monkeypatch.setenv("BH_TELEMETRY", "0")
    monkeypatch.setattr(runner, "ShoppingAdmin", lambda config: site)
    monkeypatch.setattr(runner, "BrowserSession", lambda config: session)
    monkeypatch.setattr(runner, "client_from_env", lambda results, **kwargs: llm)
    run_dir = runner.run(RunConfig(name="x"), tmp_path, confirm_paid=True)
    records = [
        json.loads(line)
        for line in (run_dir / "records.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    return run_dir, records, provider, site


def run_one_task(tmp_path, monkeypatch, session, replies):
    """runner.run on one task, with the site, the browser and the model faked."""
    write_subset(tmp_path, count=1)
    site = FakeSite()
    llm, provider, _, _ = make_client(tmp_path, replies)
    monkeypatch.setenv("BH_TELEMETRY", "0")
    monkeypatch.setattr(runner, "ShoppingAdmin", lambda config: site)
    monkeypatch.setattr(runner, "BrowserSession", lambda config: session)
    monkeypatch.setattr(runner, "client_from_env", lambda results, **kwargs: llm)
    run_dir = runner.run(RunConfig(name="x"), tmp_path)
    record = json.loads((run_dir / "records.jsonl").read_text(encoding="utf-8"))
    events = read_events(run_dir / "traces" / "100" / "events.jsonl")
    return record, events, provider, site, json.loads((run_dir / "summary.json").read_text())


def test_a_task_runs_after_the_browser_was_checked(tmp_path, monkeypatch):
    session = FakeSession()
    # The task before left a tab open; it is repaired and the task runs normally.
    session.other_tabs = ["http://site.test/admin/catalog/product/edit/id/7/"]
    session.visible = False

    record, events, _, site, summary = run_one_task(
        tmp_path, monkeypatch, session, [reply(call("finish", **FINISH_OK))]
    )

    assert record["success"]
    assert record["finish_reason"] == "finished"
    kinds = [event["type"] for event in events]
    # The check comes before the task's first observation.
    assert kinds.index("env_repaired") < kinds.index("observation")
    assert session.other_tabs == []
    assert session.url == "http://site.test/admin"
    assert session.headers == site.site.auth_headers
    row = summary["fallbacks"]["rows"]["env_repaired"]
    assert (row["triggers"], row["tasks"], row["logged"]) == (1, 1, True)


def test_a_task_whose_browser_cannot_be_prepared_is_a_harness_error_and_is_not_run(
    tmp_path, monkeypatch
):
    session = FakeSession()
    session.own = None
    session.restart_repairs = False

    record, events, provider, site, summary = run_one_task(tmp_path, monkeypatch, session, [])

    assert record["finish_reason"] == "harness_error"
    assert not record["success"]
    assert (record["steps"], record["tokens"], record["usd"]) == (0, 0, 0.0)
    assert "also after a restart" in record["error"]
    # Not run: the model was never called and nothing was scored.
    assert provider.calls == []
    assert site.scored == []
    assert [event["type"] for event in events] == ["browser_restarted", "harness_error"]
    assert events[-1]["log_version"] == LOG_VERSION
    rows = summary["fallbacks"]["rows"]
    assert rows["harness_error"]["triggers"] == 1
    assert (rows["browser_restarted"]["triggers"], rows["browser_restarted"]["recovered"]) == (1, 0)
    # The log says which version it is although the task never started.
    assert rows["new_tab"]["logged"]


def test_memory_switches_are_off_by_default_and_need_a_build_when_on():
    config = RunConfig(name="x")

    assert not config.switches.uses_memory()
    assert config.memory_build is None
    with pytest.raises(ValidationError, match="memory_build must name the build"):
        RunConfig.model_validate({"name": "x", "switches": {"skills": True}})
    with_build = RunConfig.model_validate(
        {"name": "x", "switches": {"lessons": True}, "memory_build": "2026-01-01_b"}
    )
    assert with_build.switches.uses_memory()


def test_a_task_without_memory_records_nothing_about_memory(tmp_path, monkeypatch):
    record, _, _, _, _ = run_one_task(
        tmp_path, monkeypatch, FakeSession(), [reply(call("finish", **FINISH_OK))]
    )

    assert "memory_used" not in record


# -- a browser that is lost -------------------------------------------------------

LOST = "sent 1011 (internal error); no close frame received"


class DyingSession(FakeSession):
    """A browser whose connection is lost: the reset between tasks fails until the
    browser has been restarted (if a restart helps at all)."""

    def __init__(self, restart_helps=True):
        super().__init__()
        self.dead = True
        self.restart_helps = restart_helps

    def reset_state(self, origins=()):
        if self.dead:
            raise BrowserError(f"Network.clearBrowserCookies failed: {LOST}")
        super().reset_state(origins)

    def restart(self):
        super().restart()
        self.dead = not self.restart_helps


def test_a_browser_lost_before_a_task_is_restarted_and_the_task_runs(tmp_path, monkeypatch):
    session = DyingSession()

    record, events, _provider, _, summary = run_one_task(
        tmp_path, monkeypatch, session, [reply(call("finish", **FINISH_OK))]
    )

    assert record["success"]
    assert record["finish_reason"] == "finished"
    assert record["attempts"] == 2
    assert session.restarts == 1
    kinds = [event["type"] for event in events]
    assert kinds[0] == "browser_restarted"
    assert events[0]["during"] == "task"
    assert LOST in events[0]["reason"]
    assert kinds.index("browser_restarted") < kinds.index("task_start")
    assert "harness_error" not in kinds
    assert summary["fallbacks"]["rows"]["browser_restarted"]["triggers"] == 1


def test_a_browser_lost_during_a_task_is_restarted_and_the_task_is_run_again(tmp_path, monkeypatch):
    """m2high_test_r1, task 214: the page could not be read any more in step 21."""
    real_run = runner.AgentLoop.run
    goals = []

    def lose_the_browser_once(self, goal):
        goals.append(goal)
        if len(goals) == 1:
            raise BrowserError(LOST)
        return real_run(self, goal)

    monkeypatch.setattr(runner.AgentLoop, "run", lose_the_browser_once)
    session = FakeSession()

    record, events, _provider, site, _ = run_one_task(
        tmp_path, monkeypatch, session, [reply(call("finish", **FINISH_OK))]
    )

    assert record["success"]
    assert record["attempts"] == 2
    assert len(goals) == 2
    assert session.restarts == 1
    # One log holds both attempts; the task was scored once.
    assert [event["type"] for event in events].count("browser_restarted") == 1
    assert len(site.scored) == 1
    # The site is reset before the second attempt: the first may have changed it.
    assert site.site_resets == 2


def test_a_browser_that_stays_lost_after_the_restart_is_a_harness_error(tmp_path, monkeypatch):
    session = DyingSession(restart_helps=False)

    record, events, provider, _, _ = run_one_task(tmp_path, monkeypatch, session, [])

    assert record["finish_reason"] == "harness_error"
    assert LOST in record["error"]
    assert session.restarts == 1  # one restart, one more try, then it is recorded
    assert [event["type"] for event in events] == ["browser_restarted", "harness_error"]
    assert provider.calls == []


def test_three_harness_errors_in_a_row_stop_the_run(tmp_path, monkeypatch, capsys):
    session = DyingSession(restart_helps=False)

    run_dir, records, provider, _ = run_tasks(tmp_path, monkeypatch, session, [], count=8)

    # Eight tasks were selected; the run gave up after the third.
    assert [record["finish_reason"] for record in records] == ["harness_error"] * 3
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["tasks"] == 3
    assert summary["stopped_early"] == (
        "3 tasks in a row ended in a harness error; the run was stopped with 5 of 8 tasks not run"
    )
    note = (run_dir / "STOPPED.md").read_text(encoding="utf-8")
    assert "stopped, not a complete run" in note
    assert LOST in note
    assert "stopping: 3 tasks in a row ended in a harness error" in capsys.readouterr().out
    assert provider.calls == []


def test_harness_errors_that_are_not_in_a_row_do_not_stop_the_run(tmp_path, monkeypatch):
    class Flaky(FakeSession):
        """Lost before every second task, and a restart does not bring it back in time."""

        def __init__(self):
            super().__init__()
            self.tasks = 0
            self.failing = False

        def reset_state(self, origins=()):
            if not self.failing:
                self.tasks += 1
                self.failing = self.tasks % 2 == 0
            if self.failing:
                raise BrowserError(LOST)
            super().reset_state(origins)

        def restart(self):
            super().restart()

    session = Flaky()
    original_run_task = runner.run_task

    def run_task(*args, **kwargs):
        try:
            return original_run_task(*args, **kwargs)
        finally:
            if kwargs.get("attempt") == 2:
                session.failing = False

    monkeypatch.setattr(runner, "run_task", run_task)
    replies = [reply(call("finish", **FINISH_OK)) for _ in range(3)]

    run_dir, records, _, _ = run_tasks(tmp_path, monkeypatch, session, replies, count=6)

    reasons = [record["finish_reason"] for record in records]
    assert reasons == ["finished", "harness_error"] * 3
    assert not (run_dir / "STOPPED.md").exists()


def test_a_stopped_run_ends_with_an_exit_code_of_its_own(tmp_path, monkeypatch):
    run_dir = tmp_path / "results" / "2026-01-01_x"
    run_dir.mkdir(parents=True)
    config = tmp_path / "x.json"
    config.write_text(json.dumps({"name": "x"}), encoding="utf-8")
    monkeypatch.setattr(runner, "run", lambda config, root, **kwargs: run_dir)

    assert runner.main(["--config", str(config)]) == 0
    (run_dir / "STOPPED.md").write_text("stopped", encoding="utf-8")
    assert runner.main(["--config", str(config)]) == 2
