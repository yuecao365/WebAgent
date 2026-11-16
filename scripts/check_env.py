"""Check the local shopping-admin environment end to end, without calling a model.

    uv run python scripts/check_env.py

It confirms three things: the site loads in the harness browser, a reset restores
the site's state, and the official evaluator scores a task from the harness's own
network trace. Each check prints PASS or FAIL; the exit code is 1 if any failed.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
os.environ["BH_TELEMETRY"] = "0"

from browser_agent.browser import actions  # noqa: E402
from browser_agent.browser.observation import observe  # noqa: E402
from browser_agent.browser.session import BrowserConfig, BrowserSession  # noqa: E402
from browser_agent.eval.webarena import ShoppingAdmin, SiteConfig  # noqa: E402

# Task 157, "View the details of all customers": one navigation, scored from the trace.
NAVIGATE_TASK = 157
SQL_READ = "SELECT firstname FROM customer_entity WHERE entity_id = 1"
SQL_WRITE = "UPDATE customer_entity SET firstname = 'ResetCheck' WHERE entity_id = 1"


def mysql(container: str, statement: str) -> str:
    done = subprocess.run(
        ["docker", "exec", container, "mysql", "-umagentouser", "-pMyPassword",
         "magentodb", "-N", "-e", statement],
        capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip
    return done.stdout.strip()


def report(name: str, ok: bool, detail: str) -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}", flush=True)
    return ok


def main() -> int:
    env = ShoppingAdmin(SiteConfig.from_env())
    data_dir = Path(os.environ.get("BROWSER_AGENT_DATA_DIR", "").strip() or ROOT / "data")
    browser_path = os.environ.get("BROWSER_PATH", "").strip()
    results: list[bool] = []

    env.wait_ready()
    started = time.monotonic()
    with BrowserSession(
        BrowserConfig(data_dir=data_dir, browser_path=Path(browser_path) if browser_path else None)
    ) as browser:
        print(f"browser and daemon up in {time.monotonic() - started:.1f}s", flush=True)

        browser.reset_state()
        browser.set_extra_headers(env.site.auth_headers)
        actions.goto(browser, env.site.admin_url)
        page = observe(browser)
        results.append(
            report(
                "site loads",
                "Dashboard" in page.title,
                f"{page.url} | title {page.title!r} | "
                f"{len(page.tree.splitlines())} lines, {len(page.tree)} chars",
            )
        )

        actions.goto(browser, f"{env.site.admin_url}/customer/index/")
        with tempfile.TemporaryDirectory() as tmp:
            har = Path(tmp) / "network.har"
            assert browser.recorder is not None
            entries = browser.recorder.save(har)
            right = env.evaluate(
                NAVIGATE_TASK,
                {"task_type": "NAVIGATE", "status": "SUCCESS", "retrieved_data": None},
                har,
            )
            wrong = env.evaluate(
                NAVIGATE_TASK,
                {"task_type": "RETRIEVE", "status": "SUCCESS", "retrieved_data": ["x"]},
                har,
            )
        results.append(
            report(
                "official evaluator scores a task",
                right.success and not wrong.success,
                f"task {NAVIGATE_TASK}: correct run scored {right.score}, wrong answer "
                f"scored {wrong.score} ({entries} trace entries)",
            )
        )

    before = mysql(env.site.container, SQL_READ)
    mysql(env.site.container, SQL_WRITE)
    changed = mysql(env.site.container, SQL_READ)
    seconds = env.reset()
    after = mysql(env.site.container, SQL_READ)
    results.append(
        report(
            "reset restores state",
            changed == "ResetCheck" and after == before,
            f"value {before!r} -> {changed!r} -> reset ({seconds:.0f}s) -> {after!r}",
        )
    )
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
