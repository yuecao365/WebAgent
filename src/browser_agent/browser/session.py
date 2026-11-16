"""A dedicated browser process driven through the browser-harness daemon.

The session owns its own Chromium (Chrome or Edge) with a throwaway profile, so the
user's everyday browser, profile and logins are never touched. browser-harness is
used as a library: its daemon holds the CDP connection and its helpers send input.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import time
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from browser_agent.browser.network import NetworkRecorder

_BROWSER_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)

# Reading the accessibility tree of a large admin page takes longer than the
# 5 seconds browser-harness allows a CDP call by default.
_SLOW_CDP_TIMEOUT = 60.0


class BrowserError(RuntimeError):
    """The browser or the daemon could not do what was asked."""


class Browser(Protocol):
    """What observation and actions need from a browser.

    Kept small so offline tests can substitute a fake without a real browser.
    """

    def cdp(self, method: str, **params: Any) -> dict[str, Any]: ...

    def click_at(self, x: float, y: float) -> None: ...

    def insert_text(self, text: str) -> None: ...

    def press_key(self, key: str) -> None: ...

    def wheel(self, x: float, y: float, dy: float) -> None: ...

    def settle(self) -> None: ...

    def pending_dialog(self) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class BrowserConfig:
    """How to launch and fence the browser."""

    data_dir: Path
    browser_path: Path | None = None
    headless: bool = True
    # browser-harness gives every daemon not named "default" a tab of its own, opened
    # in the background. A background tab is hidden, and Chrome neither lays out nor
    # exposes to accessibility what a hidden page adds later, so grid rows came back
    # empty. "default" attaches to the browser's own foreground tab instead. The name
    # cannot collide with a daemon of the user's: its files live under data_dir.
    name: str = "default"
    window_size: tuple[int, int] = (1280, 900)
    # Hosts the browser may resolve. Everything else fails DNS inside this browser,
    # which enforces the "local WebArena sites only" rule at the network level.
    allowed_hosts: Sequence[str] = ("localhost", "127.0.0.1")
    extra_args: Sequence[str] = field(default_factory=tuple)


def find_browser(explicit: Path | None = None) -> Path:
    """Return the browser binary: the configured one, else the first one installed."""
    if explicit is not None:
        if not explicit.exists():
            raise BrowserError(f"browser not found at {explicit}")
        return explicit
    for candidate in _BROWSER_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            return path
    raise BrowserError("no Chrome or Edge found; set BROWSER_PATH in .env")


def launch_args(config: BrowserConfig, port: int) -> list[str]:
    """Command-line flags for the dedicated browser."""
    excludes = ", ".join(f"EXCLUDE {host}" for host in config.allowed_hosts)
    args = [
        f"--remote-debugging-port={port}",
        f"--user-data-dir={config.data_dir / 'profile'}",
        f"--window-size={config.window_size[0]},{config.window_size[1]}",
        f"--host-resolver-rules=MAP * ~NOTFOUND, {excludes}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-sync",
        "--disable-extensions",
        "--password-store=basic",
        # browser-harness works in a background tab, where Chrome slows timers to
        # one per second. Script-heavy pages then take half a minute to render.
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
    ]
    if config.headless:
        args.append("--headless=new")
    args.extend(config.extra_args)
    args.append("about:blank")
    return args


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class BrowserSession:
    """Start, connect to and close one dedicated browser."""

    def __init__(self, config: BrowserConfig) -> None:
        self.config = config
        self.recorder: NetworkRecorder | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._cdp_url: str | None = None
        self._ws_url: str | None = None
        self._helpers: Any = None
        self._admin: Any = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Launch the browser, then connect the daemon and the network recorder."""
        binary = find_browser(self.config.browser_path)
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        port = _free_port()
        self._process = subprocess.Popen(
            [str(binary), *launch_args(self.config, port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.connect(f"http://127.0.0.1:{port}")

    def connect(self, cdp_url: str) -> None:
        """Attach browser-harness and the recorder to a browser listening at cdp_url."""
        self._cdp_url = cdp_url
        self._ws_url = self._wait_for_endpoint(cdp_url)
        # browser-harness reads these when its modules are imported, so they have
        # to be in the environment before the import below.
        os.environ.update(
            {
                "BH_TELEMETRY": "0",
                "BH_TAB_MARKER": "0",
                "BU_NAME": self.config.name,
                "BU_CDP_URL": cdp_url,
                "BH_HOME": str(self.config.data_dir / "bh"),
            }
        )
        from browser_harness import admin, helpers

        if self.config.name != helpers.NAME:
            raise BrowserError(
                "browser-harness was imported before the session set BU_NAME; "
                "import browser_agent.browser.session first"
            )
        self._admin, self._helpers = admin, helpers
        admin.ensure_daemon(name=self.config.name)
        self.cdp("Page.bringToFront")
        self.recorder = NetworkRecorder(self._ws_url)
        self.recorder.start()

    def close(self) -> None:
        """Stop the recorder and the daemon, then close the browser we launched."""
        if self.recorder is not None:
            self.recorder.stop()
            self.recorder = None
        if self._admin is not None:
            with contextlib.suppress(Exception):
                self._admin.restart_daemon(self.config.name)
        if self._process is not None:
            self._close_browser_process()
            self._process = None

    def __enter__(self) -> BrowserSession:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- Browser protocol --------------------------------------------------

    def cdp(self, method: str, **params: Any) -> dict[str, Any]:
        """Send one CDP command to the attached tab."""
        try:
            return self._bh.cdp(method, _response_timeout=_SLOW_CDP_TIMEOUT, **params)
        except Exception as exc:
            raise BrowserError(f"{method} failed: {exc}") from exc

    def click_at(self, x: float, y: float) -> None:
        self._guard(lambda: self._bh.click_at_xy(x, y))

    def insert_text(self, text: str) -> None:
        self._guard(lambda: self._bh.type_text(text))

    def press_key(self, key: str) -> None:
        self._guard(lambda: self._bh.press_key(key))

    def wheel(self, x: float, y: float, dy: float) -> None:
        self._guard(lambda: self._bh.scroll(x, y, dy=dy))

    def settle(self, timeout: float = 30.0) -> None:
        """Wait until the page has loaded and stopped changing, or the time is up.

        Admin pages keep building themselves after the load event: scripts load in
        chains and grids fill from XHR. The page counts as settled when it has
        loaded, the network has been idle and the element count has stayed the same
        across two looks.

        A page in the middle of a navigation, or busy running script, may not answer
        for seconds. That is not a failure of the action that caused it, so an
        unanswered question is asked again until the time is up; settle never raises.
        """
        deadline = time.monotonic() + timeout
        previous = -1
        while time.monotonic() < deadline:
            remaining = max(deadline - time.monotonic(), 0.5)
            try:
                loaded = self._bh.wait_for_load(timeout=min(remaining, 15.0))
                self._bh.wait_for_network_idle(timeout=min(remaining, 10.0), idle_ms=500)
                count = self._element_count()
            except Exception:
                previous = -1
                time.sleep(0.5)
                continue
            if loaded and count == previous:
                return
            previous = count
            time.sleep(0.3)

    def _element_count(self) -> int:
        result = self._bh.cdp(
            "Runtime.evaluate",
            expression="document.getElementsByTagName('*').length",
            returnByValue=True,
        )
        return int(result.get("result", {}).get("value") or 0)

    def pending_dialog(self) -> dict[str, Any] | None:
        # page_info() reports an open native dialog instead of evaluating script,
        # which would hang because the dialog freezes the page's JS thread.
        return self._guard(self._bh.page_info).get("dialog")

    # -- task isolation ----------------------------------------------------

    def set_extra_headers(self, headers: Mapping[str, str]) -> None:
        """Send these headers with every request of the attached tab."""
        self.cdp("Network.setExtraHTTPHeaders", headers=dict(headers))

    def reset_state(self, origins: Sequence[str] = ()) -> None:
        """Drop cookies, stored page data and the recorded traffic between tasks.

        origins are the sites whose local storage and caches are cleared; pages keep
        UI state there that would otherwise carry over to the next task.
        """
        self.cdp("Network.clearBrowserCookies")
        for origin in origins:
            self.cdp("Storage.clearDataForOrigin", origin=origin, storageTypes="all")
        self.cdp("Page.navigate", url="about:blank")
        if self.recorder is not None:
            self.recorder.clear()

    # -- internals ---------------------------------------------------------

    @property
    def _bh(self) -> Any:
        if self._helpers is None:
            raise BrowserError("session is not connected")
        return self._helpers

    def _guard(self, call: Any) -> Any:
        try:
            return call()
        except BrowserError:
            raise
        except Exception as exc:
            raise BrowserError(str(exc)) from exc

    @staticmethod
    def _wait_for_endpoint(cdp_url: str, timeout: float = 30.0) -> str:
        deadline = time.monotonic() + timeout
        last: Exception | None = None
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"{cdp_url}/json/version", timeout=2) as resp:
                    return json.loads(resp.read())["webSocketDebuggerUrl"]
            except (OSError, KeyError, ValueError) as exc:
                last = exc
                time.sleep(0.2)
        raise BrowserError(f"browser did not open {cdp_url}: {last}")

    def _close_browser_process(self) -> None:
        assert self._process is not None
        try:
            from websockets.sync.client import connect

            if self._ws_url is not None:
                with connect(self._ws_url, open_timeout=5) as ws:
                    ws.send(json.dumps({"id": 1, "method": "Browser.close"}))
            self._process.wait(timeout=10)
        except Exception:
            self._process.kill()


def origin_of(url: str) -> str:
    """scheme://host[:port] of a URL, the unit the navigation guard compares."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}".lower()
