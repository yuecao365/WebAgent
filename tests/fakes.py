"""Stand-ins for the model, the tool executor and the browser. No network, no browser."""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from browser_agent.browser.session import BrowserError
from browser_agent.harness.llm import LLMClient, Pricing, Reply, SpendLedger, ToolCall, Usage
from browser_agent.harness.tools import FinishArgs, PageView, ToolOutcome

FIXTURES = Path(__file__).parent / "fixtures"
_ids = itertools.count(1)

# $1 per million input tokens and $10 per million output tokens keep the sums easy.
PRICING = Pricing(input=1.0, output=10.0, cached_input=0.1, cache_write=1.25)
FINISH_OK = {
    "task_type": "RETRIEVE",
    "status": "SUCCESS",
    "retrieved_data": '["42"]',
    "error_details": None,
}


def call(name: str, **arguments: Any) -> ToolCall:
    return ToolCall(f"call_{next(_ids)}", name, arguments, json.dumps(arguments))


def reply(*calls: ToolCall, text: str = "", usage: Usage | None = None, stop: str = "tool_calls"):
    return Reply(text, tuple(calls), usage or Usage(input_tokens=1000, output_tokens=100), stop)


class ScriptedProvider:
    """Returns the queued replies in order; an exception in the queue is raised."""

    def __init__(self, replies: list[Any]) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def complete(self, system, messages, tools, options):
        self.calls.append(
            {
                "system": system,
                "messages": list(messages),
                "tools": [t.name for t in tools],
                "options": options,
            }
        )
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_client(tmp_path: Path, replies: list[Any], budget_usd: float = 100.0, **kwargs: Any):
    provider = ScriptedProvider(replies)
    ledger = SpendLedger(tmp_path / "results", budget_usd)
    sleeps: list[float] = []
    client = LLMClient(provider, PRICING, ledger, "fake-model", sleep=sleeps.append, **kwargs)
    return client, provider, ledger, sleeps


class FakeExecutor:
    """A ToolExecutor whose outcomes and pages are scripted.

    Without a script every action succeeds and leads to a new page, so a test only
    has to describe the calls it cares about. `pages` overrides what view() returns.
    """

    def __init__(
        self, outcomes: list[ToolOutcome] | None = None, pages: list[str] | None = None
    ) -> None:
        self.outcomes = list(outcomes or [])
        self.pages = list(pages or [])
        self.executed: list[tuple[str, Any]] = []
        self.recovered: list[str] = []
        self.views = 0
        self._page = 1

    def view(self) -> PageView:
        self.views += 1
        if self.pages:
            name = self.pages.pop(0) if len(self.pages) > 1 else self.pages[0]
        else:
            name = f"p{self._page}"
        return PageView(f"page {name}", f"fp-{name}", f"http://site.test/{name}", f"Title {name}")

    def execute(self, name: str, arguments: Any) -> ToolOutcome:
        self.executed.append((name, arguments))
        if name == "finish":
            try:
                finish = FinishArgs.model_validate(arguments)
            except ValidationError as exc:
                return ToolOutcome(False, f"Invalid arguments for finish: {exc.errors()[0]['msg']}")
            return ToolOutcome(True, "Task finished.", finish=finish)
        if name == "write_note":
            return ToolOutcome(True, "Note saved.", note=arguments["text"])
        if self.outcomes:
            outcome = self.outcomes.pop(0)
        else:
            outcome = ToolOutcome(True, f"{name} done.", acted=True)
        if outcome.ok and outcome.acted:
            self._page += 1
        return outcome

    def recover(self, url: str) -> ToolOutcome:
        self.recovered.append(url)
        return ToolOutcome(True, f"Returned to the last page that worked: {url}", navigated=True)


def failed(message: str = "click failed: no such element") -> ToolOutcome:
    return ToolOutcome(False, message, acted=True)


def navigated(
    message: str = "Clicked [1]. Now on: Orders (http://site.test/orders)",
) -> ToolOutcome:
    return ToolOutcome(True, message, navigated=True, acted=True)


class FakeBrowser:
    """Implements the Browser protocol over a described page."""

    def __init__(self, nodes: list[dict[str, Any]] | None = None) -> None:
        self.nodes = nodes or []
        self.url = "http://site.test/admin/"
        self.title = "Admin"
        # Identity of the loaded document; a navigation replaces it.
        self.document = 1
        # ref -> what the page reports about the element behind it
        self.elements: dict[int, dict[str, Any]] = {}
        self.quads: dict[int, list[list[float]]] = {}
        self.options: dict[int, list[str]] = {}
        # refs whose click loads a new document, with the URL it leads to
        self.links: dict[int, str] = {}
        # refs whose click opens a new tab, with the URL the tab goes to
        self.new_tab_links: dict[int, str] = {}
        # addresses of the tabs open besides the agent's
        self.other_tabs: list[str] = []
        self.visible = True
        # -- what the environment check looks at --
        # url -> the nodes of the page there; other addresses show self.nodes
        self.pages: dict[str, list[dict[str, Any]]] = {}
        # url -> where the site redirects it
        self.redirects: dict[str, str] = {}
        # how many navigations the tab ignores, staying where it is
        self.ignored_navigations = 0
        self.requested = ""
        self.own: str | None = "AGENT"
        # what the browser still holds for the site, in words
        self.stored: list[str] = []
        self.clearing_works = True
        self.stays_hidden = False
        self.restart_repairs = True
        self.headers: dict[str, str] = {}
        self.restarts = 0
        # the order in which the check touched the browser
        self.steps: list[str] = []
        # ref -> the value the field shows whatever was typed into it
        self.masks: dict[int, str] = {}
        self.navigate_error: str | None = None
        self.dialog: dict[str, Any] | None = None
        self.cdp_calls: list[tuple[str, dict[str, Any]]] = []
        self.clicks: list[tuple[float, float]] = []
        self.typed: list[str] = []
        self.keys: list[str] = []
        self.wheels: list[float] = []
        self.scripts: list[str] = []
        self.settled = 0
        self._last_ref: int | None = None

    def element(self, ref: int, tag: str = "button", **flags: bool) -> None:
        self.elements[ref] = {
            "tag": tag,
            "option": tag == "option",
            "select": tag == "select",
            "editable": tag in ("input", "textarea"),
            "disabled": False,
            **flags,
        }
        self.quads.setdefault(ref, [[10, 20, 110, 20, 110, 60, 10, 60]])

    # -- Browser protocol --------------------------------------------------

    def cdp(self, method: str, **params: Any) -> dict[str, Any]:
        self.cdp_calls.append((method, params))
        if method == "Runtime.evaluate":
            info: dict[str, Any] = {"w": 1280, "h": 900}
            if "location.href" in params["expression"]:
                info.update(url=self.url, title=self.title, sy=0, ph=2000, doc=self.document)
            return {"result": {"value": json.dumps(info)}}
        if method == "Accessibility.getFullAXTree":
            return {"nodes": self.pages.get(self.url, self.nodes)}
        if method == "Page.navigate":
            if self.navigate_error:
                return {"errorText": self.navigate_error}
            self.steps.append(f"goto {params['url']}")
            if self.ignored_navigations:
                self.ignored_navigations -= 1
                return {"frameId": "F"}
            self.requested = params["url"]
            self.url = self.redirects.get(params["url"], params["url"])
            self.document += 1
            return {"frameId": "F"}
        if method == "DOM.resolveNode":
            if params["backendNodeId"] not in self.elements:
                raise BrowserError("DOM.resolveNode failed: No node with given id found")
            self._last_ref = params["backendNodeId"]
            return {"object": {"objectId": str(params["backendNodeId"])}}
        if method == "DOM.getContentQuads":
            return {"quads": self.quads.get(params["backendNodeId"], [])}
        if method == "Runtime.callFunctionOn":
            return {"result": {"value": self._script(int(params["objectId"]), params)}}
        return {}

    def _script(self, ref: int, params: dict[str, Any]) -> Any:
        source = params["functionDeclaration"]
        self.scripts.append(source)
        if "tagName.toLowerCase" in source:
            return self.elements[ref]
        if "function(wanted)" in source:
            wanted = params["arguments"][0]["value"].lower()
            labels = self.options.get(ref, [])
            match = next((label for label in labels if label.lower() == wanted), None)
            return {"ok": True, "chosen": match} if match else {"ok": False, "options": labels}
        if "closest('select')" in source:
            return True
        if "'value' in el" in source:
            # What the field holds after typing; `masks` models a field that alters it.
            typed = self.typed[-1] if self.typed else ""
            return self.masks.get(ref, typed)
        return None

    def click_at(self, x: float, y: float) -> None:
        self.clicks.append((x, y))
        target = self.links.get(self._last_ref or -1)
        if target is not None:
            self.url = target
            self.title = "Next page"
            self.document += 1
        opened = self.new_tab_links.get(self._last_ref or -1)
        if opened is not None:
            # A new tab opens in front and hides the agent's tab.
            self.other_tabs.append(opened)
            self.visible = False

    def insert_text(self, text: str) -> None:
        self.typed.append(text)

    def press_key(self, key: str) -> None:
        self.keys.append(key)

    def wheel(self, x: float, y: float, dy: float) -> None:
        self.wheels.append(dy)

    def settle(self) -> None:
        self.settled += 1

    def pending_dialog(self) -> dict[str, Any] | None:
        dialog, self.dialog = self.dialog, None
        return dialog

    def close_other_tabs(self) -> list[str]:
        closed, self.other_tabs = self.other_tabs, []
        if closed:
            self.visible = True
        return closed

    # -- what the environment check needs ------------------------------------

    def own_tab(self) -> str | None:
        return self.own

    def is_visible(self) -> bool:
        return self.visible

    def bring_to_front(self) -> None:
        self.steps.append("front")
        self.visible = not self.stays_hidden

    def stored_site_data(self, origin: str) -> list[str]:
        self.steps.append("storage")
        # Reading the storage drops the extra headers, as the real session does.
        self.headers = {}
        return list(self.stored)

    def clear_site_data(self, origins: Any) -> None:
        self.steps.append("clear")
        if self.clearing_works:
            self.stored = []

    def set_extra_headers(self, headers: Any) -> None:
        self.headers = dict(headers)

    def navigation(self) -> tuple[str, str]:
        return self.requested, self.url

    def restart(self) -> None:
        self.steps.append("restart")
        self.restarts += 1
        self.headers = {}
        if self.restart_repairs:
            self.own, self.other_tabs, self.visible, self.stored = "AGENT", [], True, []
            self.stays_hidden, self.ignored_navigations = False, 0
            self.requested, self.url = "", "about:blank"


class FakeRecorder:
    """Stands in for the network recorder: an empty trace."""

    def __init__(self) -> None:
        self.cleared = 0

    def clear(self) -> None:
        self.cleared += 1

    def har(self) -> dict[str, Any]:
        return {"log": {"entries": []}}

    def save(self, path: Path) -> int:
        path.write_text(json.dumps(self.har()), encoding="utf-8")
        return 0


class FakeSession(FakeBrowser):
    """A FakeBrowser with the parts of BrowserSession the runner uses around a task."""

    def __init__(self, nodes: list[dict[str, Any]] | None = None) -> None:
        super().__init__(nodes)
        self.recorder = FakeRecorder()
        self.notify: Any = None
        self.resets = 0

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *exc: object) -> None:
        pass

    def reset_state(self, origins: Any = ()) -> None:
        self.resets += 1
        self.stored = [] if self.clearing_works else self.stored
        self.cdp("Page.navigate", url="about:blank")
        self.steps.clear()
        self.recorder.clear()


class FakeSite:
    """Stands in for ShoppingAdmin: one site, tasks that start at its admin root."""

    def __init__(self, url: str = "http://site.test", intent: str = "Find it") -> None:
        from browser_agent.eval.webarena import AgentTask, Score, SiteConfig

        self.site = SiteConfig(url=url, env_ctrl_url=url)
        self._task, self._score = AgentTask, Score
        self.intent = intent
        self.start_urls: dict[int, str] = {}
        self.answering: list[str] = []
        self.site_resets = 0
        # What the evaluator says of every answer.
        self.evaluation = True
        self.scored: list[tuple[int, dict[str, Any]]] = []

    def task(self, task_id: int) -> Any:
        start = self.start_urls.get(task_id, self.site.admin_url)
        return self._task(task_id, 1, self.intent, start)

    def reset(self) -> float:
        self.site_resets += 1
        return 0.0

    def restore_ui_state(self) -> None:
        pass

    def not_answering(self) -> list[str]:
        return list(self.answering)

    def evaluate(self, task_id: int, response: dict[str, Any], har_path: Path) -> Any:
        self.scored.append((task_id, response))
        score = 1.0 if self.evaluation else 0.0
        return self._score(self.evaluation, score, "scored", {"score": score})


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# -- a small shop: three pages saved from the local site ----------------------

SHOP_BASE = "http://site.test/admin"
SHOP_GRID = f"{SHOP_BASE}/sales/order/"
SHOP_ORDER = f"{SHOP_BASE}/sales/order/view/order_id/299/"
SHOP_REPORT = f"{SHOP_BASE}/reports/report_sales/sales/"
# The "View" link of order 000000299 in the saved grid.
SHOP_VIEW_299 = 1842


def shop_browser(session: bool = False) -> Any:
    """A fake browser on the order grid; "View" of order 299 leads to its page."""
    browser = FakeSession() if session else FakeBrowser()
    browser.pages = {
        SHOP_GRID: load_fixture("ax_orders_grid.json"),
        SHOP_ORDER: load_fixture("ax_order_view.json"),
        SHOP_REPORT: load_fixture("ax_sales_report.json"),
    }
    browser.url = SHOP_GRID
    browser.element(SHOP_VIEW_299, tag="a")
    browser.links[SHOP_VIEW_299] = SHOP_ORDER
    return browser
