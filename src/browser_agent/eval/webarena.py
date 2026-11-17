"""WebArena Verified, shopping-admin site: tasks, reset, scoring and the task subset.

Scoring is always done by the official `webarena-verified` evaluator; nothing here
decides whether a task succeeded.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import time
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SITE = "shopping_admin"
SITE_PLACEHOLDER = "__SHOPPING_ADMIN__"
AUTO_LOGIN_HEADER = "X-M2-Admin-Auto-Login"
# Pinned by tag so every run uses the same site data (digest sha256:d0531dd27ed9...).
DEFAULT_IMAGE = "am1n3e/webarena-verified-shopping_admin:0.1.0"
DEFAULT_CONTAINER = "webarena-verified-shopping_admin"
# Magento admin grids fetch their rows from this endpoint with an XHR.
GRID_DATA_PATH = "/mui/index/render"
# Requests that write but do not change the shop's data: a grid saving its filters,
# sorting and paging for the signed-in admin. That state is restored between tasks.
UI_STATE_PATHS = ("/mui/bookmark/save",)
UI_STATE_TABLE = "ui_bookmark"
_UI_STATE_DUMP = "/tmp/browser_agent_ui_state.sql"
# Database account of the benchmark image; a published test value, not a secret.
_MYSQL = "-umagentouser -pMyPassword magentodb"


class SiteError(RuntimeError):
    """The local site could not be reset or reached."""


@dataclass(frozen=True)
class SiteConfig:
    """Where the local shopping-admin site runs and how to sign in to it."""

    url: str = "http://localhost:7780"
    env_ctrl_url: str = "http://localhost:7781"
    image: str = DEFAULT_IMAGE
    container: str = DEFAULT_CONTAINER
    # Published test credentials of the benchmark image; not a secret.
    username: str = "admin"
    password: str = "admin1234"

    @classmethod
    def from_env(cls) -> SiteConfig:
        defaults = cls()
        return cls(
            url=os.environ.get("WEBARENA_SHOPPING_ADMIN_URL", "").strip().rstrip("/")
            or defaults.url,
            env_ctrl_url=os.environ.get("WEBARENA_SHOPPING_ADMIN_ENV_CTRL_URL", "")
            .strip()
            .rstrip("/")
            or defaults.env_ctrl_url,
            # A second site next to the first needs its own container name and ports.
            container=os.environ.get("WEBARENA_SHOPPING_ADMIN_CONTAINER", "").strip()
            or defaults.container,
        )

    @property
    def admin_url(self) -> str:
        return f"{self.url}/admin"

    @property
    def auth_headers(self) -> dict[str, str]:
        return {AUTO_LOGIN_HEADER: f"{self.username}:{self.password}"}


@dataclass(frozen=True)
class AgentTask:
    """What the agent is given: no reference answer, no evaluator settings."""

    task_id: int
    template_id: int
    intent: str
    start_url: str


@dataclass(frozen=True)
class Score:
    success: bool
    score: float
    status: str
    detail: dict[str, Any]


CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _run_command(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=600, check=False)


class ShoppingAdmin:
    """The local site: start and reset its container, render tasks, score answers."""

    def __init__(
        self,
        site: SiteConfig | None = None,
        run_command: CommandRunner = _run_command,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.site = site or SiteConfig()
        self._run = run_command
        self._sleep = sleep
        self._wa: Any = None

    # -- tasks -------------------------------------------------------------

    @property
    def wa(self) -> Any:
        """The official API object, created on first use because its import is slow."""
        if self._wa is None:
            from webarena_verified.api import WebArenaVerified
            from webarena_verified.types.config import WebArenaVerifiedConfig

            self._wa = WebArenaVerified(
                config=WebArenaVerifiedConfig(
                    environments={
                        SITE_PLACEHOLDER: {
                            "urls": [self.site.admin_url],
                            "use_header_login": True,
                            "credentials": {
                                "username": self.site.username,
                                "password": self.site.password,
                            },
                        }
                    }
                )
            )
        return self._wa

    def task(self, task_id: int) -> AgentTask:
        task = self.wa.get_task(task_id)
        start = task.start_urls[0].replace(SITE_PLACEHOLDER, self.site.admin_url)
        return AgentTask(task.task_id, task.intent_template_id, task.intent, start)

    # -- environment -------------------------------------------------------

    def reset(self, timeout: float = 420.0) -> float:
        """Restore the site to its initial state; returns the seconds it took.

        WebArena Verified resets a site by deleting its container and starting a
        new one from the image (the env-ctrl service has no reset endpoint), so the
        same is done here.
        """
        started = time.monotonic()
        self._run(["docker", "rm", "-f", self.site.container])
        site, ctrl = urlparse(self.site.url), urlparse(self.site.env_ctrl_url)
        result = self._run(
            [
                "docker", "run", "-d",
                "--name", self.site.container,
                "-p", f"127.0.0.1:{site.port or 80}:80",
                "-p", f"127.0.0.1:{ctrl.port or 8877}:8877",
                "-e", f"WA_ENV_CTRL_EXTERNAL_SITE_URL={self.site.url}",
                self.site.image,
            ]
        )  # fmt: skip
        if result.returncode != 0:
            raise SiteError(f"docker run failed: {result.stderr.strip()}")
        self.wait_ready(timeout)
        self._in_container(f"mysqldump {_MYSQL} {UI_STATE_TABLE} > {_UI_STATE_DUMP}")
        return time.monotonic() - started

    def restore_ui_state(self) -> None:
        """Put the admin's saved grid filters back as they were after the last reset.

        A task that only reads still leaves its filters, sorting and paging behind,
        because the grids save them on the server. The next task would open a grid
        that is already filtered. Restoring one small table is enough to undo that
        and takes well under a second, so no reset is needed for it.
        """
        self._in_container(f"mysql {_MYSQL} < {_UI_STATE_DUMP}")

    def _in_container(self, shell_command: str) -> None:
        result = self._run(["docker", "exec", self.site.container, "bash", "-c", shell_command])
        if result.returncode != 0:
            raise SiteError(f"`{shell_command}` failed in the container: {result.stderr.strip()}")

    def wait_ready(self, timeout: float = 420.0) -> None:
        """Block until the services are healthy and the admin signs in twice in a row."""
        deadline = time.monotonic() + timeout
        streak = 0
        while time.monotonic() < deadline:
            streak = streak + 1 if self._healthy() and self._signs_in() else 0
            if streak >= 2:
                return
            self._sleep(2.0)
        raise SiteError(f"{self.site.url} was not ready after {timeout:.0f}s")

    def not_answering(self) -> list[str]:
        """What does not answer right now, in words; empty when the site is up.

        One look, no waiting: a run should not start against a site that is down or
        in the middle of a reset.
        """
        problems = []
        if not self._healthy():
            problems.append(
                f"the control service of {self.site.container} does not answer at "
                f"{self.site.env_ctrl_url}"
            )
        if not self._signs_in():
            problems.append(f"the site does not sign the admin in at {self.site.admin_url}")
        return problems

    def _healthy(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.site.env_ctrl_url}/status", timeout=10) as resp:
                return bool(json.loads(resp.read()).get("success"))
        except (OSError, ValueError):
            return False

    def _signs_in(self) -> bool:
        request = urllib.request.Request(self.site.admin_url, headers=self.site.auth_headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as resp:
                # Signed in means the redirect to the dashboard, not the login form.
                return resp.status == 200 and "dashboard" in resp.url
        except (OSError, urllib.error.HTTPError):
            return False

    # -- scoring -----------------------------------------------------------

    def evaluate(self, task_id: int, response: dict[str, Any], har_path: Path) -> Score:
        """Score an answer and its network trace with the official evaluator."""
        result = self.wa.evaluate_task(
            task_id=task_id, agent_response=response, network_trace=har_path
        )
        detail = result.model_dump(mode="json")
        return Score(
            success=float(result.score) >= 1.0,
            score=float(result.score),
            status=str(detail.get("status")),
            detail=detail,
        )


# ---------------------------------------------------------------------------
# Subset
# ---------------------------------------------------------------------------


def expected_answer(task: dict[str, Any]) -> tuple[str, str]:
    """(task type, expected status) from a task's answer evaluator."""
    for evaluator in task["eval"]:
        if evaluator["evaluator"] == "AgentResponseEvaluator":
            expected = evaluator["expected"]
            return str(expected["task_type"]).lower(), str(expected["status"])
    raise ValueError(f"task {task['task_id']} has no AgentResponseEvaluator")


def is_state_changing(task: dict[str, Any]) -> bool:
    """Whether doing the task may change the shop's data, read off its evaluators.

    A task whose network check expects a write (any method but GET, or a request
    body) is checked against the site's state and is state-changing. So is a task
    whose expected answer is of type MUTATE even when it has no network check: two
    tasks ask for a change the site refuses, and an agent may still try. A task
    checked only by its answer, or by a page navigation, is read-only.
    """
    if expected_answer(task)[0] == "mutate":
        return True
    for evaluator in task["eval"]:
        if evaluator["evaluator"] != "NetworkEventEvaluator":
            continue
        expected = evaluator["expected"]
        if (expected.get("http_method") or "GET").upper() != "GET" or expected.get("post_data"):
            return True
    return False


def unexpected_writes(har_entries: Sequence[dict[str, Any]]) -> list[str]:
    """Requests in a trace that may have changed the shop's data.

    Used after a read-only task: an agent can change something it was not asked to.
    Saving grid filters does not count; that state is restored between tasks.
    """
    writes = []
    for entry in har_entries:
        request = entry["request"]
        path = urlparse(request["url"]).path
        if request["method"].upper() in ("GET", "HEAD", "OPTIONS"):
            continue
        if any(marker in path for marker in UI_STATE_PATHS):
            continue
        writes.append(f"{request['method']} {path}")
    return writes


def scorable(task: dict[str, Any]) -> bool:
    """Whether the official evaluator can pass this task at all.

    For a NAVIGATE task, evaluator 1.2.3 compares only the last page navigation of the
    trace. Tasks whose expected request is the grid's data call (an XHR) therefore
    fail even with a correct trace; checked with a hand-built correct trace of task 676.
    """
    if expected_answer(task)[0] != "navigate":
        return True
    return not any(
        GRID_DATA_PATH in str(evaluator["expected"].get("url", ""))
        for evaluator in task["eval"]
        if evaluator["evaluator"] == "NetworkEventEvaluator"
    )


def build_subset(
    tasks: Sequence[dict[str, Any]],
    quotas: dict[str, int],
    per_template: int = 4,
    seed: int = 0,
    max_similarity: float = 0.8,
) -> dict[str, Any]:
    """Choose templates and tasks for the experiments, deterministically.

    1. Keep single-site shopping-admin tasks whose expected status is SUCCESS, so a
       template's tasks all exercise the same procedure.
    2. Drop templates with a task the evaluator cannot pass (see scorable).
    3. Keep templates with at least per_template such tasks and a single task type.
    4. For each task type take quotas[type] templates in a seeded random order,
       skipping a template whose wording is nearly the same as one already taken.
    5. From each template take the first per_template tasks by id; the first is the
       "learn" task, the others are "test".
    """
    by_template: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        if list(task["sites"]) == [SITE] and expected_answer(task)[1] == "SUCCESS":
            by_template[task["intent_template_id"]].append(task)
    unscorable = sorted(
        template_id
        for template_id, members in by_template.items()
        if not all(scorable(task) for task in members)
    )
    for template_id in unscorable:
        del by_template[template_id]

    candidates: dict[str, list[int]] = defaultdict(list)
    for template_id in sorted(by_template):
        members = sorted(by_template[template_id], key=lambda t: t["task_id"])
        by_template[template_id] = members
        types = {expected_answer(task)[0] for task in members}
        if len(members) >= per_template and len(types) == 1:
            candidates[types.pop()].append(template_id)

    chosen: list[tuple[str, int]] = []
    taken_wording: list[str] = []
    for task_type in sorted(quotas):
        order = list(candidates.get(task_type, []))
        # One generator per type, so a change in one type's candidates leaves the
        # other types' choice as it was.
        random.Random(f"{seed}:{task_type}").shuffle(order)
        picked = 0
        for template_id in order:
            if picked == quotas[task_type]:
                break
            wording = by_template[template_id][0]["intent_template"]
            if any(
                SequenceMatcher(None, wording, w).ratio() > max_similarity for w in taken_wording
            ):
                continue
            taken_wording.append(wording)
            chosen.append((task_type, template_id))
            picked += 1
        if picked < quotas[task_type]:
            raise ValueError(
                f"only {picked} of {quotas[task_type]} {task_type} templates available"
            )

    templates, entries = [], []
    for task_type, template_id in sorted(chosen, key=lambda item: item[1]):
        members = by_template[template_id][:per_template]
        templates.append(
            {
                "template_id": template_id,
                "task_type": task_type,
                "intent_template": members[0]["intent_template"],
                "task_ids": [task["task_id"] for task in members],
            }
        )
        for position, task in enumerate(members):
            entries.append(
                {
                    "task_id": task["task_id"],
                    "template_id": template_id,
                    "split": "learn" if position == 0 else "test",
                    "task_type": task_type,
                    "state_changing": is_state_changing(task),
                    "intent": task["intent"],
                }
            )
    return {
        "site": SITE,
        "rules": {
            "quotas": quotas,
            "per_template": per_template,
            "seed": seed,
            "max_similarity": max_similarity,
            "unscorable_templates": unscorable,
        },
        "templates": templates,
        "tasks": entries,
    }


def dataset_tasks() -> list[dict[str, Any]]:
    """Every task of the installed WebArena Verified dataset, as plain dicts."""
    from webarena_verified.api import WebArenaVerified

    return [task.model_dump(mode="json") for task in WebArenaVerified().get_tasks()]


def load_subset(path: Path) -> list[dict[str, Any]]:
    """The task entries of a subset file."""
    return json.loads(path.read_text(encoding="utf-8"))["tasks"]
