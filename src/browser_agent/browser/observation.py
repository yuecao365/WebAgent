"""Read the current page: its accessibility tree, plain and complete.

An Observation keeps the raw tree, so that the components in `context/` can render
it in other ways (pruned, truncated, as a diff). The rendering here is the full
outline: every line that carries content, each with a ref the model can act on.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

from browser_agent.browser.session import Browser

# Wrapper roles that say nothing when they have no name. Their children are kept
# and lifted one level, so no content is lost.
_STRUCTURAL_ROLES = frozenset({"generic", "none", "presentation", "InlineTextBox", "LineBreak"})
SKIP_SUBTREE_ROLES = frozenset({"InlineTextBox", "LineBreak"})
# Boolean and tri-state properties worth showing; the rest is layout noise.
SHOWN_PROPERTIES = (
    "disabled",
    "checked",
    "selected",
    "expanded",
    "pressed",
    "required",
    "invalid",
    "focused",
    "readonly",
)

# timeOrigin is fixed when a document starts loading, so it tells a reload or a new
# page apart from changes inside the same document.
_PAGE_INFO_JS = (
    "JSON.stringify({url: location.href, title: document.title, "
    "w: innerWidth, h: innerHeight, sy: Math.round(scrollY), "
    "ph: document.documentElement.scrollHeight, doc: performance.timeOrigin})"
)


def value_of(field_: dict[str, Any] | None) -> Any:
    """The value inside one of CDP's {type, value} wrappers."""
    return None if field_ is None else field_.get("value")


def node_ref(node: dict[str, Any]) -> str:
    """The ref shown for a node; "-" when there is no element behind it."""
    return f"[{node['backendDOMNodeId']}]" if "backendDOMNodeId" in node else "[-]"


def node_states(node: dict[str, Any], name: str) -> list[str]:
    """The value and the set states of a node, as shown after its name."""
    parts: list[str] = []
    value = value_of(node.get("value"))
    if value not in (None, "") and str(value) != name:
        parts.append(f"value={json.dumps(str(value), ensure_ascii=False)}")
    for prop in node.get("properties", []):
        if prop.get("name") not in SHOWN_PROPERTIES:
            continue
        prop_value = value_of(prop.get("value"))
        if prop_value in (False, "false", None):
            continue
        if prop_value in (True, "true"):
            parts.append(prop["name"])
        else:
            parts.append(f"{prop['name']}={prop_value}")
    return parts


def _line(node: dict[str, Any]) -> str:
    role = value_of(node.get("role")) or "unknown"
    name = (value_of(node.get("name")) or "").strip()
    parts = [node_ref(node), role]
    if name:
        parts.append(json.dumps(name, ensure_ascii=False))
    return " ".join(parts + node_states(node, name))


def render_ax_tree(nodes: list[dict[str, Any]]) -> str:
    """Render CDP accessibility nodes as an indented outline, one node per line."""
    by_id = {node["nodeId"]: node for node in nodes}
    child_ids = {cid for node in nodes for cid in node.get("childIds", [])}
    roots = [node for node in nodes if node["nodeId"] not in child_ids]
    lines: list[str] = []

    # An explicit stack: admin pages nest deeper than Python's recursion limit likes.
    stack: list[tuple[dict[str, Any], int, str | None]] = [
        (root, 0, None) for root in reversed(roots)
    ]
    while stack:
        node, depth, parent_name = stack.pop()
        role = value_of(node.get("role")) or ""
        if role in SKIP_SUBTREE_ROLES:
            continue
        name = (value_of(node.get("name")) or "").strip()
        hidden = node.get("ignored", False) or (role in _STRUCTURAL_ROLES and not name)
        # A text node that only repeats its parent's name adds nothing.
        redundant = role == "StaticText" and name == parent_name
        shown = not hidden and not redundant
        if shown:
            lines.append(" " * depth + _line(node))
        child_depth = depth + 1 if shown else depth
        child_parent_name = name if shown else parent_name
        for child_id in reversed(node.get("childIds", [])):
            child = by_id.get(child_id)
            if child is not None:
                stack.append((child, child_depth, child_parent_name))
    return "\n".join(lines)


def cut(text: str, max_chars: int | None, how_to_get_more: str = "") -> str:
    """Shorten text to max_chars, saying how much was left out."""
    if max_chars is None or len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    hint = f"; {how_to_get_more}" if how_to_get_more else ""
    return f"{text[:max_chars]}\n[cut: {omitted} more characters not shown{hint}]"


@dataclass(frozen=True)
class Observation:
    """One reading of the page."""

    url: str
    title: str
    nodes: list[dict[str, Any]] = field(repr=False)
    viewport_height: int = 0
    scroll_y: int = 0
    page_height: int = 0
    dialog: str | None = None
    # Identity of the loaded document; it changes on navigation and reload.
    document: str = ""

    @cached_property
    def tree(self) -> str:
        """The full outline of the page."""
        return render_ax_tree(self.nodes)

    def header(self) -> str:
        lines = [f"URL: {self.url}", f"Title: {self.title}"]
        if self.page_height > self.viewport_height:
            lines.append(f"Scroll: {self.scroll_y} of {self.page_height - self.viewport_height} px")
        if self.dialog:
            lines.append(f"Dialog (accepted automatically): {self.dialog}")
        return "\n".join(lines)

    def render(self, max_chars: int | None = None) -> str:
        """Header and full outline, the plain view of the page."""
        return f"{self.header()}\n\n{cut(self.tree, max_chars)}"

    def fingerprint(self) -> str:
        """Identity of the page content, used to notice that nothing changed."""
        digest = hashlib.sha256(f"{self.url}\n{self.tree}".encode()).hexdigest()
        return digest[:16]


def observe(browser: Browser) -> Observation:
    """Read the page the browser is on."""
    dialog_text: str | None = None
    dialog = browser.pending_dialog()
    if dialog is not None:
        # A native dialog freezes the page; nothing can be read until it is closed.
        dialog_text = f"{dialog.get('type', 'dialog')}: {dialog.get('message', '')}"
        browser.cdp("Page.handleJavaScriptDialog", accept=True)

    evaluated = browser.cdp("Runtime.evaluate", expression=_PAGE_INFO_JS, returnByValue=True)
    info = json.loads(evaluated.get("result", {}).get("value") or "{}")
    nodes = browser.cdp("Accessibility.getFullAXTree").get("nodes", [])
    return Observation(
        url=info.get("url", ""),
        title=info.get("title", ""),
        nodes=nodes,
        viewport_height=int(info.get("h", 0)),
        scroll_y=int(info.get("sy", 0)),
        page_height=int(info.get("ph", 0)),
        dialog=dialog_text,
        document=str(info.get("doc", "")),
    )
