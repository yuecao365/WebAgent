"""Record the browser's HTTP traffic as a HAR file.

The WebArena Verified evaluator scores navigation and mutation tasks from a network
trace. browser-harness keeps only the last 500 CDP events and hands them out once,
which a single admin page load overflows, so the recorder listens on its own CDP
connection and never competes with the daemon for events.
"""

from __future__ import annotations

import contextlib
import json
import threading
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# The evaluator ignores static assets; leaving them out keeps traces small.
_STATIC_RESOURCE_TYPES = frozenset({"Image", "Stylesheet", "Font", "Script", "Media"})
_MAX_POST_DATA_BYTES = 2_000_000


def _header_list(headers: dict[str, Any] | None) -> list[dict[str, str]]:
    return [{"name": str(k), "value": str(v)} for k, v in (headers or {}).items()]


def _lookup(headers: dict[str, Any] | None, name: str) -> str:
    for key, value in (headers or {}).items():
        if str(key).lower() == name:
            return str(value)
    return ""


class HarBuilder:
    """Turn CDP Network events into HAR entries.

    A request id is reused across a redirect chain, and the real headers (cookies,
    sec-fetch-*) arrive in separate ExtraInfo events that may come before or after
    the main event. Entries and ExtraInfo events are therefore paired by their
    position within each request id.
    """

    def __init__(self) -> None:
        self.clear()

    def feed(self, method: str, params: dict[str, Any], session_id: str | None = None) -> None:
        """Consume one CDP event; events of other domains are ignored."""
        handler = {
            "Network.requestWillBeSent": self._on_request,
            "Network.requestWillBeSentExtraInfo": self._on_request_extra,
            "Network.responseReceived": self._on_response,
            "Network.responseReceivedExtraInfo": self._on_response_extra,
        }.get(method)
        if handler is not None:
            handler(f"{session_id or ''}:{params.get('requestId', '')}", params)

    def clear(self) -> None:
        self._entries: list[dict[str, Any]] = []
        self._by_request: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._request_extra: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._response_extra: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def entries(self) -> list[dict[str, Any]]:
        """HAR entries for every request that got a response, in request order."""
        out = []
        for raw in self._entries:
            if raw["response"] is None or raw["resource_type"] in _STATIC_RESOURCE_TYPES:
                continue
            out.append(self._to_har(raw))
        return out

    def har(self) -> dict[str, Any]:
        return {
            "log": {
                "version": "1.2",
                "creator": {"name": "browser-agent", "version": "0.1.0"},
                "entries": self.entries(),
            }
        }

    # -- event handlers ----------------------------------------------------

    def _on_request(self, key: str, params: dict[str, Any]) -> None:
        chain = self._by_request[key]
        redirect = params.get("redirectResponse")
        if redirect is not None and chain:
            # The previous hop of this chain is answered by the redirect itself.
            chain[-1]["response"] = redirect
        entry = {
            "request": params.get("request", {}),
            "response": None,
            "resource_type": params.get("type", "Other"),
            "wall_time": params.get("wallTime"),
            "index": len(chain),
            "key": key,
        }
        chain.append(entry)
        self._entries.append(entry)

    def _on_request_extra(self, key: str, params: dict[str, Any]) -> None:
        self._request_extra[key].append(params)

    def _on_response(self, key: str, params: dict[str, Any]) -> None:
        chain = self._by_request.get(key)
        if chain:
            chain[-1]["response"] = params.get("response", {})
            chain[-1]["resource_type"] = params.get("type", chain[-1]["resource_type"])

    def _on_response_extra(self, key: str, params: dict[str, Any]) -> None:
        self._response_extra[key].append(params)

    # -- HAR conversion ----------------------------------------------------

    def _to_har(self, raw: dict[str, Any]) -> dict[str, Any]:
        key, index = raw["key"], raw["index"]
        request, response = raw["request"], raw["response"]

        request_headers = dict(request.get("headers") or {})
        extras = self._request_extra.get(key, [])
        if index < len(extras):
            request_headers.update(extras[index].get("headers") or {})

        response_headers = dict(response.get("headers") or {})
        status = response.get("status", 0)
        extras = self._response_extra.get(key, [])
        if index < len(extras):
            response_headers.update(extras[index].get("headers") or {})
            status = extras[index].get("statusCode", status)

        har_request: dict[str, Any] = {
            "method": request.get("method", "GET"),
            "url": request.get("url", ""),
            "httpVersion": response.get("protocol", "HTTP/1.1"),
            "headers": _header_list(request_headers),
            "queryString": [],
            "cookies": [],
            "headersSize": -1,
            "bodySize": -1,
        }
        post_data = request.get("postData")
        if post_data is not None:
            har_request["postData"] = {
                "mimeType": _lookup(request_headers, "content-type"),
                "text": post_data,
            }

        redirect_url = _lookup(response_headers, "location") if 300 <= status < 400 else ""
        started = datetime.fromtimestamp(raw["wall_time"] or 0, tz=UTC).isoformat()
        return {
            "startedDateTime": started,
            "time": 0,
            "request": har_request,
            "response": {
                "status": status,
                "statusText": response.get("statusText", ""),
                "httpVersion": response.get("protocol", "HTTP/1.1"),
                "headers": _header_list(response_headers),
                "cookies": [],
                "content": {"size": -1, "mimeType": response.get("mimeType", "")},
                "redirectURL": redirect_url,
                "headersSize": -1,
                "bodySize": -1,
            },
            "cache": {},
            "timings": {"send": 0, "wait": 0, "receive": 0},
            "_resourceType": raw["resource_type"],
        }


class NetworkRecorder:
    """Listen to every page of one browser and build a HAR from its traffic."""

    def __init__(self, ws_url: str) -> None:
        self._ws_url = ws_url
        self._builder = HarBuilder()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._ws: Any = None
        self._next_id = 0
        self._stopping = False

    def start(self) -> None:
        from websockets.sync.client import connect

        self._ws = connect(self._ws_url, max_size=None, open_timeout=10)
        self._send("Target.setDiscoverTargets", {"discover": True})
        self._thread = threading.Thread(target=self._pump, name="har-recorder", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping = True
        if self._ws is not None:
            with contextlib.suppress(Exception):
                self._ws.close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def clear(self) -> None:
        with self._lock:
            self._builder.clear()

    def har(self) -> dict[str, Any]:
        with self._lock:
            return self._builder.har()

    def save(self, path: Path) -> int:
        """Write the trace to path and return the number of entries."""
        har = self.har()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(har), encoding="utf-8")
        return len(har["log"]["entries"])

    # -- internals ---------------------------------------------------------

    def _send(self, method: str, params: dict[str, Any], session_id: str | None = None) -> None:
        self._next_id += 1
        message: dict[str, Any] = {"id": self._next_id, "method": method, "params": params}
        if session_id:
            message["sessionId"] = session_id
        self._ws.send(json.dumps(message))

    def _pump(self) -> None:
        try:
            for raw in self._ws:
                self._handle(json.loads(raw))
        except Exception:
            if not self._stopping:
                raise

    def _handle(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        if method is None:
            return
        params = message.get("params", {})
        if method == "Target.targetCreated":
            info = params.get("targetInfo", {})
            if info.get("type") == "page":
                self._send("Target.attachToTarget", {"targetId": info["targetId"], "flatten": True})
        elif method == "Target.attachedToTarget":
            self._send(
                "Network.enable",
                {"maxPostDataSize": _MAX_POST_DATA_BYTES},
                session_id=params.get("sessionId"),
            )
        elif method.startswith("Network."):
            with self._lock:
                self._builder.feed(method, params, message.get("sessionId"))
