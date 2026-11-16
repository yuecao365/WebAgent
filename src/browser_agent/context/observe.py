"""Smaller views of a page: pruned outline, truncated lists, diff against the last step.

Each is a switch, off by default. With every switch off the view is the complete
outline, exactly as `Observation.render` gives it.

- prune: keep what can be acted on and what can be read. Table rows become one line
  each, wrappers and repeated text disappear, and only elements that can be acted on
  carry a ref.
- truncate: show the first few of a long run of rows, options or similar items, with
  a count of the rest. `read_page(section=ref)` shows a part of the page in full.
- diff: when the page is the same document as at the last step, show only the lines
  that changed.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from typing import Any

from browser_agent.browser.observation import (
    SKIP_SUBTREE_ROLES,
    Observation,
    cut,
    node_ref,
    node_states,
    value_of,
)

# Roles a user acts on. They keep their ref in the pruned view.
INTERACTIVE_ROLES = frozenset(
    {
        "button", "link", "textbox", "searchbox", "combobox", "listbox", "option",
        "checkbox", "radio", "switch", "slider", "spinbutton", "menuitem",
        "menuitemcheckbox", "menuitemradio", "tab", "treeitem", "columnheader",
    }
)  # fmt: skip
# Interactive roles whose children are their own choices, not their label.
_CHOICE_HOLDERS = frozenset({"combobox", "listbox"})
# Structure worth one line of its own: it tells the model where it is on the page.
_LANDMARK_ROLES = frozenset(
    {
        "heading", "dialog", "alertdialog", "alert", "status", "table", "grid", "menu",
        "menubar", "tablist", "navigation", "form", "group", "region", "tabpanel",
        "toolbar", "image",
    }
)  # fmt: skip
# Landmarks that are kept even without a name.
_ALWAYS_SHOWN = frozenset({"dialog", "alertdialog", "alert", "table", "grid", "menu"})
_SECTION_MAX_CHARS = 40_000
# Below this size a section is shown complete even when the page view is pruned.
_SECTION_FULL_CHARS = 6_000


@dataclass(frozen=True)
class ViewOptions:
    """Which observation components are on, and their limits."""

    prune: bool = False
    truncate: bool = False
    diff: bool = False
    # How many of a run are shown before the rest is counted instead.
    max_rows: int = 20
    max_options: int = 8
    max_items: int = 40
    # A diff larger than this share of the page is not worth reading as a diff.
    max_diff_share: float = 0.5
    max_chars: int = 300_000


@dataclass
class _Block:
    """The lines one child subtree produced, and the role that produced them."""

    role: str
    lines: list[str]
    selected: bool = False


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _name(node: dict[str, Any]) -> str:
    return _clean(value_of(node.get("name")) or "")


def _role(node: dict[str, Any]) -> str:
    return value_of(node.get("role")) or ""


def _is_selected(node: dict[str, Any]) -> bool:
    return any(
        prop.get("name") == "selected" and value_of(prop.get("value")) in (True, "true")
        for prop in node.get("properties", [])
    )


def _interactive(node: dict[str, Any]) -> bool:
    if _role(node) in INTERACTIVE_ROLES:
        return True
    # A plain element made focusable is usually a hand-built control.
    return _role(node) not in ("RootWebArea", "StaticText") and any(
        prop.get("name") == "focusable" and value_of(prop.get("value")) in (True, "true")
        for prop in node.get("properties", [])
    )


class _Renderer:
    """Walks an accessibility tree once and produces the lines of a view."""

    def __init__(self, nodes: list[dict[str, Any]], options: ViewOptions) -> None:
        self._options = options
        self._by_id = {node["nodeId"]: node for node in nodes}
        child_ids = {cid for node in nodes for cid in node.get("childIds", [])}
        self._roots = [node for node in nodes if node["nodeId"] not in child_ids]
        self._by_ref = {
            node["backendDOMNodeId"]: node for node in nodes if "backendDOMNodeId" in node
        }

    def page(self) -> list[str]:
        return self._lines(self._inner(self._roots, 0, None, False))

    def section(self, ref: int) -> list[str] | None:
        node = self._by_ref.get(ref)
        return None if node is None else self._lines(self._blocks(node, 0, None, False))

    # -- walking -----------------------------------------------------------

    def _children(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        return [self._by_id[cid] for cid in node.get("childIds", []) if cid in self._by_id]

    def _collect(
        self,
        children: list[dict[str, Any]],
        depth: int,
        holder: dict[str, Any] | None,
        mute_text: bool,
    ) -> list[_Block]:
        """The blocks of some siblings, as they come. Used when their parent is not
        shown and they join the parent's own siblings."""
        blocks: list[_Block] = []
        for child in children:
            blocks.extend(self._blocks(child, depth, holder, mute_text))
        return blocks

    def _inner(
        self,
        children: list[dict[str, Any]],
        depth: int,
        holder: dict[str, Any] | None,
        mute_text: bool,
    ) -> list[_Block]:
        """The finished content of a shown node: text joined, long runs counted once."""
        blocks = _merge_text(self._collect(children, depth, holder, mute_text))
        return self._truncate(blocks, depth, holder) if self._options.truncate else blocks

    def _blocks(
        self, node: dict[str, Any], depth: int, holder: dict[str, Any] | None, mute_text: bool
    ) -> list[_Block]:
        """The blocks of one node: its own line with its children, or just the children."""
        role = _role(node)
        if role in SKIP_SUBTREE_ROLES or depth > 300:
            return []
        if "backendDOMNodeId" in node:
            holder = node
        if node.get("ignored"):
            return self._collect(self._children(node), depth, holder, mute_text)
        if not self._options.prune:
            return self._full_blocks(node, depth, holder)
        return self._pruned_blocks(node, depth, holder, mute_text)

    def _full_blocks(
        self, node: dict[str, Any], depth: int, holder: dict[str, Any] | None
    ) -> list[_Block]:
        role, name = _role(node), _name(node)
        if role in ("generic", "none", "presentation") and not name:
            return self._collect(self._children(node), depth, holder, False)
        children = [
            child
            for child in self._children(node)
            # A text node that only repeats its parent's name adds nothing.
            if not (_role(child) == "StaticText" and _name(child) == name)
        ]
        line = " " * depth + self._line(node, with_ref=True)
        inner = self._inner(children, depth + 1, holder, False)
        return [_Block(role, [line, *self._lines(inner)], _is_selected(node))]

    def _pruned_blocks(
        self, node: dict[str, Any], depth: int, holder: dict[str, Any] | None, mute_text: bool
    ) -> list[_Block]:
        role, name = _role(node), _name(node)
        indent = " " * depth
        if role == "StaticText":
            return [] if mute_text or not name else [_Block("text", [indent + name])]
        if role == "row":
            return [_Block("row", [indent + self._row(node)])]
        if _interactive(node):
            line = indent + self._line(node, with_ref=True)
            # The label of a control repeats its name; only its choices are kept.
            inner = self._inner(self._children(node), depth + 1, holder, mute_text=bool(name))
            if role not in _CHOICE_HOLDERS:
                inner = [block for block in inner if block.role != "text"]
            return [_Block(role, [line, *self._lines(inner)], _is_selected(node))]
        if role in _LANDMARK_ROLES and (name or role in _ALWAYS_SHOWN):
            line = indent + self._line(node, with_ref=False)
            # A heading or an image is its name; its text children would repeat it.
            mute = mute_text or role in ("heading", "image")
            inner = self._inner(self._children(node), depth + 1, holder, mute)
            return [_Block(role, [line, *self._lines(inner)])]
        return self._collect(self._children(node), depth, holder, mute_text)

    # -- lines -------------------------------------------------------------

    @staticmethod
    def _line(node: dict[str, Any], with_ref: bool) -> str:
        role, name = _role(node) or "unknown", _name(node)
        parts = [node_ref(node), role] if with_ref else [role]
        if name:
            parts.append(json.dumps(name, ensure_ascii=False))
        return " ".join(parts + node_states(node, name))

    def _row(self, node: dict[str, Any]) -> str:
        """A table row on one line: its cells, with what can be acted on inside them."""
        cells = [self._cell(cell) for cell in self._children(node) if not cell.get("ignored")]
        while cells and not cells[-1]:
            cells.pop()
        return f"{node_ref(node)} row: {' | '.join(cells)}"

    def _cell(self, cell: dict[str, Any]) -> str:
        controls = self._controls(cell)
        if _role(cell) == "columnheader":
            # Headers can be clicked to sort; the ref is enough, the role is implied.
            return f"{node_ref(cell)} {_name(cell)}"
        if _interactive(cell):
            return self._line(cell, with_ref=True)
        if not controls:
            return _name(cell)
        text = _name(cell)
        shown = " ".join(self._line(control, with_ref=True) for control in controls)
        # A cell whose only content is its control needs no separate text.
        repeats = len(controls) == 1 and text == _name(controls[0])
        return shown if repeats or not text else f"{text} {shown}"

    def _controls(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        stack = list(reversed(self._children(node)))
        while stack:
            current = stack.pop()
            if _role(current) in SKIP_SUBTREE_ROLES:
                continue
            if not current.get("ignored") and _interactive(current):
                found.append(current)
                continue
            stack.extend(reversed(self._children(current)))
        return found

    @staticmethod
    def _lines(blocks: list[_Block]) -> list[str]:
        return [line for block in blocks for line in block.lines]

    # -- truncation --------------------------------------------------------

    def _limit(self, role: str) -> int | None:
        if role == "row":
            return self._options.max_rows
        if role == "option":
            return self._options.max_options
        if role in INTERACTIVE_ROLES:
            return self._options.max_items
        return None

    def _truncate(
        self, blocks: list[_Block], depth: int, holder: dict[str, Any] | None
    ) -> list[_Block]:
        """Keep the first few blocks of each long run of one role, and count the rest."""
        counts: dict[str, int] = {}
        for block in blocks:
            counts[block.role] = counts.get(block.role, 0) + 1
        kept: list[_Block] = []
        seen: dict[str, int] = {}
        dropped: dict[str, int] = {}
        for block in blocks:
            limit = self._limit(block.role)
            seen[block.role] = seen.get(block.role, 0) + 1
            over = limit is not None and counts[block.role] > limit and seen[block.role] > limit
            # The chosen option stays visible wherever it is in the list.
            if over and not block.selected:
                dropped[block.role] = dropped.get(block.role, 0) + 1
                continue
            kept.append(block)
        for role, count in dropped.items():
            where = f"section={holder['backendDOMNodeId']}" if holder else "a section ref"
            kept.append(
                _Block(
                    "cut",
                    [
                        f"{' ' * depth}… {count} more {role}s not shown; "
                        f"read_page with {where} lists them all"
                    ],
                )
            )
        return kept


def _merge_text(blocks: list[_Block]) -> list[_Block]:
    """Join neighbouring text lines of the same depth into one line."""
    merged: list[_Block] = []
    for block in blocks:
        previous = merged[-1] if merged else None
        if block.role == "text" and previous is not None and previous.role == "text":
            previous.lines[-1] = f"{previous.lines[-1]} {block.lines[0].strip()}"
        else:
            merged.append(_Block(block.role, list(block.lines), block.selected))
    return merged


def _diff(before: list[str], after: list[str]) -> list[str]:
    """The changed lines, with one unchanged line around each change for bearings."""
    lines: list[str] = []
    for line in difflib.unified_diff(before, after, n=1, lineterm=""):
        if line.startswith(("---", "+++")):
            continue
        lines.append("…" if line.startswith("@@") else line)
    return lines


class PageRenderer:
    """Renders observations according to the switches; keeps the last page for diffs."""

    def __init__(self, options: ViewOptions | None = None) -> None:
        self.options = options or ViewOptions()
        self._last_document: str | None = None
        self._last_lines: list[str] = []

    def render(self, observation: Observation, previous: Observation | None) -> str:
        """The text of the page for the prompt's tail."""
        options = self.options
        if not (options.prune or options.truncate or options.diff):
            return observation.render(options.max_chars)

        if options.prune or options.truncate:
            lines = _Renderer(observation.nodes, options).page()
        else:
            lines = observation.tree.splitlines()
        same_document = bool(observation.document) and observation.document == self._last_document
        before, self._last_lines = self._last_lines, lines
        self._last_document = observation.document

        header = observation.header()
        if options.prune:
            header += (
                "\nShown: what can be acted on and what can be read. "
                "read_page with a section ref shows that part in full."
            )
        if options.diff and same_document and previous is not None:
            changed = _diff(before, lines)
            if not changed:
                return f"{header}\n\nThe page is the same as at your last step."
            if len(changed) <= max(40, options.max_diff_share * len(lines)):
                return (
                    f"{header}\n\nSame page as at your last step. Only the changes are "
                    "shown: lines with + are new, lines with - are gone. Call read_page "
                    "with section null to see the whole page.\n" + "\n".join(changed)
                )
        return f"{header}\n\n{cut(chr(10).join(lines), options.max_chars)}"

    def section(self, observation: Observation, ref: int) -> str | None:
        """Everything under one element, with nothing counted away.

        A small part is shown complete, so that an element the pruned view leaves
        out can still be found. A large part keeps the page's own style, or a long
        table would not fit.
        """
        full = _Renderer(observation.nodes, ViewOptions()).section(ref)
        if full is None:
            return None
        lines = full
        if self.options.prune and len("\n".join(full)) > _SECTION_FULL_CHARS:
            lines = _Renderer(observation.nodes, ViewOptions(prune=True)).section(ref) or full
        return cut(
            "\n".join(lines),
            _SECTION_MAX_CHARS,
            "call read_page with the ref of a smaller part inside it",
        )


__all__ = ["PageRenderer", "ViewOptions"]
