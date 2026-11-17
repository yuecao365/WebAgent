"""A fixed fake episode, run through the real runner, and the requests it sends.

The site, the browser and the OpenAI SDK are faked; everything between them is the
code under test: the runner, the switches and their defaults, the loop, the tools,
the observation views, the prompt layout and the Responses API adapter. What comes
out is the list of request bodies handed to the SDK, in order.

tests/fixtures/requests_fa8aef6.jsonl holds those bodies as produced by commit
fa8aef6, the code that ran baseline_test_r1 and r2. It was written by running this
file against a checkout of that commit:

    git worktree add <dir> fa8aef6
    PYTHONPATH=<dir>/src python tests/request_episode.py tests/fixtures/requests_fa8aef6.jsonl

Each line is one request body as compact ASCII JSON, keys in the order they were
built, so that a comparison of the lines is a comparison of the bytes.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import openai

from browser_agent.eval import runner
from browser_agent.eval.runner import RunConfig

from fakes import FakeSession, FakeSite

SITE = "http://site.test"
START = f"{SITE}/admin"
DASHBOARD = f"{SITE}/admin/admin/dashboard/"
ORDERS = f"{SITE}/admin/sales/order/"
ORDER = f"{SITE}/admin/sales/order/view/order_id/150/"
INTENT = "What is the grand total of order 000000150, and what is its status?"
RUN_NAME = "2026-01-01_fixture"
TASK_ID = 7

# Refs are 100 + the node id (see node() below).
ORDERS_LINK = 104
SEARCH_BOX = 203
TOTALS_SECTION = 304
PRODUCT_LINK = 105


def node(node_id: int, role: str, name: str = "", children: Any = (), **extra: Any) -> dict:
    return {
        "nodeId": str(node_id),
        "role": {"value": role},
        "name": {"value": name},
        "childIds": [str(child) for child in children],
        "backendDOMNodeId": 100 + node_id,
        **extra,
    }


def dashboard() -> list[dict]:
    return [
        node(1, "RootWebArea", "Dashboard / Magento Admin", children=[2, 6]),
        node(2, "navigation", "Menu", children=[3, 4, 5]),
        node(3, "link", " DASHBOARD"),
        node(4, "link", " SALES"),
        node(5, "link", "Joust Duffle Bag"),
        node(6, "main", "", children=[7, 8]),
        node(7, "heading", "Dashboard", children=[9]),
        node(9, "StaticText", "Dashboard"),
        node(8, "StaticText", "Lifetime Sales $0.00 — Average Order $0.00"),
    ]


def orders(rows: int = 200) -> list[dict]:
    """A grid long enough for the default view to cut it."""
    nodes = [
        node(
            101,
            "RootWebArea",
            "Orders / Operations / Sales / Magento Admin",
            children=[102, 103, 104],
        ),
        node(102, "heading", "Orders", children=[108]),
        node(108, "StaticText", "Orders"),
        node(103, "textbox", "Search by keyword"),
        node(104, "table", "", children=[105, *range(110, 110 + rows)]),
        node(105, "row", "", children=[106, 109, 107]),
        node(106, "columnheader", "ID"),
        node(109, "columnheader", "Bill-to Name, Purchase Date, Grand Total"),
        node(107, "columnheader", "Status"),
    ]
    for index in range(rows):
        base = 1000 + index * 10
        nodes += [
            node(
                110 + index,
                "row",
                "",
                children=[base, base + 7, base + 8, base + 9, base + 1, base + 2],
            ),
            node(base + 7, "cell", f"Customer Number {index}"),
            node(base + 8, "cell", f"Mar {index % 28 + 1}, 2023 10:{index % 60:02d}:00 AM"),
            node(base + 9, "cell", f"${30 + index}.39"),
            node(base, "cell", f"{index:09d}", children=[base + 5]),
            node(base + 5, "StaticText", f"{index:09d}"),
            node(base + 1, "cell", "Pending" if index % 3 else "Complete", children=[base + 6]),
            node(base + 6, "StaticText", "Pending" if index % 3 else "Complete"),
            node(base + 2, "cell", "View", children=[base + 3]),
            node(base + 3, "link", "View", children=[base + 4]),
            node(base + 4, "StaticText", "View"),
        ]
    return nodes


def order() -> list[dict]:
    return [
        node(201, "RootWebArea", "#000000150 / Orders / Magento Admin", children=[202, 204]),
        node(202, "heading", "#000000150", children=[203]),
        node(203, "StaticText", "#000000150"),
        node(204, "region", "Order Totals", children=[205, 206, 207]),
        node(205, "StaticText", "Subtotal $31.39"),
        node(206, "StaticText", "Shipping & Handling $5.00"),
        node(207, "StaticText", "Grand Total $36.39 — “Pending”"),
    ]


def episode_browser() -> FakeSession:
    """The fake site as a browser sees it: three pages and the elements acted on."""
    browser = FakeSession()
    browser.redirects[START] = DASHBOARD
    browser.pages = {DASHBOARD: dashboard(), ORDERS: orders(), ORDER: order()}
    browser.element(ORDERS_LINK, tag="a")
    browser.links[ORDERS_LINK] = ORDERS
    browser.element(SEARCH_BOX, tag="input")
    browser.element(PRODUCT_LINK, tag="a")
    return browser


def _response(*items: Any, input_tokens: int = 1200, cached: int = 0) -> SimpleNamespace:
    """A reply in the shape of the SDK's Response, as far as the adapter reads it."""
    return SimpleNamespace(
        output=list(items),
        status="completed",
        incomplete_details=None,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=40,
            input_tokens_details=SimpleNamespace(cached_tokens=cached),
            output_tokens_details=SimpleNamespace(reasoning_tokens=8),
        ),
    )


def _call(number: int, name: str, **arguments: Any) -> SimpleNamespace:
    return SimpleNamespace(
        type="function_call",
        call_id=f"call_{number:03d}",
        name=name,
        arguments=json.dumps(arguments),
    )


def _reasoning(number: int) -> SimpleNamespace:
    return SimpleNamespace(
        type="reasoning", id=f"rs_{number:03d}", encrypted_content=f"ENCRYPTED-{number:03d}"
    )


def _text(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text=text)])


def episode_replies(first_click: int = ORDERS_LINK) -> list[SimpleNamespace]:
    """Ten model turns that use every tool, fail once and answer without a call once."""
    finish = {
        "task_type": "RETRIEVE",
        "status": "SUCCESS",
        "retrieved_data": '[{"grand_total": "$36.39", "status": "Pending"}]',
        "error_details": None,
    }
    return [
        _response(_reasoning(1), _call(1, "click", ref=first_click)),
        _response(_call(2, "type", ref=SEARCH_BOX, text="000000150", submit=True), cached=1024),
        _response(
            _reasoning(3), _call(3, "read_page", section=None, find="000000150"), cached=1024
        ),
        _response(_call(4, "click", ref=9999), cached=2048),
        _response(
            _call(5, "write_note", text="Order 150 is in the grid; open its page for the total.")
        ),
        _response(_call(6, "scroll", direction="down"), cached=2048),
        _response(_call(7, "goto", url=ORDER), cached=2048),
        _response(_call(8, "read_page", section=TOTALS_SECTION, find=None), cached=3072),
        _response(_text("The grand total is $36.39 and the order is pending."), cached=3072),
        _response(_reasoning(10), _call(10, "finish", **finish), cached=3072),
    ]


class RecordingSDK:
    """Stands in for openai.OpenAI: keeps every request body and replays the replies."""

    def __init__(self, replies: list[SimpleNamespace]) -> None:
        self.replies = list(replies)
        self.requests: list[dict[str, Any]] = []
        self.responses = self

    def create(self, **request: Any) -> SimpleNamespace:
        self.requests.append(copy.deepcopy(request))
        return self.replies.pop(0)


_MODEL_ENV = {
    "LLM_API_KEY": "not-a-key",
    "LLM_MODEL": "fixture-model",
    "LLM_PRICE_INPUT_PER_MTOK": "1",
    "LLM_PRICE_OUTPUT_PER_MTOK": "10",
    "BUDGET_USD": "100",
    "BH_TELEMETRY": "0",
}


def run_episode(
    workdir: Path,
    browser: FakeSession | None = None,
    replies: list[SimpleNamespace] | None = None,
    config: RunConfig | None = None,
) -> tuple[list[dict[str, Any]], Path]:
    """Run the episode with runner.run; return the request bodies and the run directory.

    The config has only a name, so every switch, the API and the reasoning effort are
    whatever the code under test defaults to. No LLM_* setting of the machine reaches
    the run.
    """
    (workdir / "configs").mkdir(parents=True)
    entry = {
        "task_id": TASK_ID,
        "template_id": 1,
        "split": "test",
        "task_type": "retrieve",
        "intent": INTENT,
        "state_changing": False,
    }
    (workdir / "configs" / "subset.json").write_text(
        json.dumps({"tasks": [entry]}), encoding="utf-8"
    )
    session = browser or episode_browser()
    site = FakeSite(url=SITE, intent=INTENT)
    sdk = RecordingSDK(replies or episode_replies())
    run_dir = workdir / "results" / RUN_NAME

    def fixed_run_dir(results: Path, name: str) -> Path:
        # The run's name is part of the prompt cache key, so it must not hold the date.
        run_dir.mkdir(parents=True)
        return run_dir

    environment = {k: v for k, v in os.environ.items() if not k.startswith("LLM_")} | _MODEL_ENV
    with (
        patch.dict(os.environ, environment, clear=True),
        patch.object(openai, "OpenAI", lambda **kwargs: sdk),
        patch.object(runner, "ShoppingAdmin", lambda site_config: site),
        patch.object(runner, "BrowserSession", lambda browser_config: session),
        patch.object(runner, "new_run_dir", fixed_run_dir),
        # The run-start check does not exist in fa8aef6; create=True covers both.
        patch.object(runner, "preflight", lambda env: None, create=True),
    ):
        runner.run(config or RunConfig(name="fixture"), workdir)
    return sdk.requests, run_dir


def as_lines(requests: list[dict[str, Any]]) -> list[str]:
    """Each request body as the bytes compared: compact ASCII JSON, key order kept."""
    return [json.dumps(request, ensure_ascii=True, separators=(",", ":")) for request in requests]


if __name__ == "__main__":
    import tempfile

    import browser_agent

    target = Path(sys.argv[1])
    with tempfile.TemporaryDirectory() as tmp:
        bodies, _ = run_episode(Path(tmp))
    target.write_text("\n".join(as_lines(bodies)) + "\n", encoding="ascii", newline="\n")
    print(f"{len(bodies)} request bodies from {Path(browser_agent.__file__).parent} -> {target}")
