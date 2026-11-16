"""Read the current page as text: the accessibility tree, plain and complete.

Every line that carries content gets a ref the model can act on. Nothing is pruned
or summarised here; that belongs to the context components built later, which take
this observation as their input.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from browser_agent.browser.session import Browser

# Wrapper roles that say nothing when they have no name. Their children are kept
# and lifted one level, so no content is lost.
_STRUCTURAL_ROLES = frozenset({"generic", "none", "presentation", "InlineTextBox", "LineBreak"})
_SKIP_SUBTREE_ROLES = frozenset({"InlineTextBox", "LineBreak"})
# Boolean and tri-state properties worth showing; the rest is layout noise.
_SHOWN_PROPERTIES = (
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

_PAGE_INFO_JS = (
    "JSON.stringify({url: location.href, title: document.title, "
    "w: innerWidth, h: innerHeight, sy: Math.round(scrollY), "
    "ph: document.documentElement.scrollHeight})"
)


@dataclass(frozen=True)
class Observation:
    """One reading of the page."""

    url: str
    title: str
    tree: str
    viewport_height: int
    scroll_y: int
    page_height: int
    dialog: str | None = None

    def render(self) -> str:
        """The text shown to the model."""
        lines = [f"URL: {self.url}", f"Title: {self.title}"]
        if self.page_height > self.viewport_height:
            lines.append(f"Scroll: {self.scroll_y} of {self.page_height - self.viewport_height} px")
        if self.dialog:
            lines.append(f"Dialog (accepted automatically): {self.dialog}")
        lines.append("")
        lines.append(self.tree)
        return "\n".join(lines)

    def fingerprint(self) -> str:
        """Identity of the page content, used to notice that nothing changed."""
        digest = hashlib.sha256(f"{self.url}\n{self.tree}".encode()).hexdigest()
        return digest[:16]


def _value(field: dict[str, Any] | None) -> Any:
    return None if field is None else field.get("value")


def _line(node: dict[str, Any]) -> str:
    role = _value(node.get("role")) or "unknown"
    name = (_value(node.get("name")) or "").strip()
    parts = [f"[{node['backendDOMNodeId']}]" if "backendDOMNodeId" in node else "[-]", role]
    if name:
        parts.append(json.dumps(name, ensure_ascii=False))
    value = _value(node.get("value"))
    if value not in (None, "") and str(value) != name:
        parts.append(f"value={json.dumps(str(value), ensure_ascii=False)}")
    for prop in node.get("properties", []):
        if prop.get("name") not in _SHOWN_PROPERTIES:
            continue
        prop_value = _value(prop.get("value"))
        if prop_value in (False, "false", None):
            continue
        parts.append(
            prop["name"] if prop_value in (True, "true") else f"{prop['name']}={prop_value}"
        )
    return " ".join(parts)


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
        role = _value(node.get("role")) or ""
        if role in _SKIP_SUBTREE_ROLES:
            continue
        name = (_value(node.get("name")) or "").strip()
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


def observe(browser: Browser, max_chars: int | None = None) -> Observation:
    """Read the page the browser is on.

    max_chars is a safety limit against pages too large for any model context; the
    cut is stated in the text so the model knows the page continues.
    """
    dialog_text: str | None = None
    dialog = browser.pending_dialog()
    if dialog is not None:
        # A native dialog freezes the page; nothing can be read until it is closed.
        dialog_text = f"{dialog.get('type', 'dialog')}: {dialog.get('message', '')}"
        browser.cdp("Page.handleJavaScriptDialog", accept=True)

    evaluated = browser.cdp("Runtime.evaluate", expression=_PAGE_INFO_JS, returnByValue=True)
    info = json.loads(evaluated.get("result", {}).get("value") or "{}")
    nodes = browser.cdp("Accessibility.getFullAXTree").get("nodes", [])
    tree = render_ax_tree(nodes)
    if max_chars is not None and len(tree) > max_chars:
        omitted = len(tree) - max_chars
        tree = f"{tree[:max_chars]}\n[observation cut: {omitted} more characters not shown]"
    return Observation(
        url=info.get("url", ""),
        title=info.get("title", ""),
        tree=tree,
        viewport_height=int(info.get("h", 0)),
        scroll_y=int(info.get("sy", 0)),
        page_height=int(info.get("ph", 0)),
        dialog=dialog_text,
    )
