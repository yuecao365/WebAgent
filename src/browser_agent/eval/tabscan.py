"""Find, in the traces of an old run, pages that were loaded outside the agent's tab.

Since log version 3 a tab opened by an action leaves a new_tab event. Older runs
have no such event, but their network traces cover every tab of the browser, and
their event logs say where the agent's own tab was after each step. A page that was
loaded as a document and that the agent's tab never showed was loaded somewhere
else: in a second tab, or in a frame.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any
from urllib.parse import urldefrag

_NOW_ON = re.compile(r"Now on: .*\((\S+)\)")


def _plain(url: str) -> str:
    return urldefrag(url).url.rstrip("/")


def shown_urls(events: Sequence[dict[str, Any]]) -> set[str]:
    """Every address the agent's tab was seen at: observations, results and gotos."""
    seen: set[str] = set()
    for event in events:
        kind = event.get("type")
        if kind == "observation" and event.get("url"):
            seen.add(_plain(event["url"]))
        elif kind == "tool_result":
            seen.update(_plain(url) for url in _NOW_ON.findall(event.get("content") or ""))
        elif kind == "tool_call" and event.get("name") == "goto":
            url = (event.get("arguments") or {}).get("url")
            if isinstance(url, str):
                seen.add(_plain(url))
    return seen


def unshown_documents(
    events: Sequence[dict[str, Any]], har_entries: Sequence[dict[str, Any]]
) -> list[str]:
    """Documents that were loaded but that the agent's tab was never seen at.

    Redirect hops are left out: only the page a navigation ends on is a document
    somebody was shown.
    """
    seen = shown_urls(events)
    unshown = []
    for entry in har_entries:
        if entry.get("_resourceType") != "Document":
            continue
        if 300 <= entry.get("response", {}).get("status", 0) < 400:
            continue
        url = entry.get("request", {}).get("url", "")
        if _plain(url) not in seen:
            unshown.append(url)
    return unshown
