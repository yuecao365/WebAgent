"""Find one element of a page by what it is, not by its ref.

A ref is a number that belongs to one page load. A skill has to work on the next load
too, so it names an element by its role and accessible name, optionally inside a table
row that shows a given text, or inside a named section of the page.

A locator must match exactly one element. No match, or several, is an error that says
what was found instead: a skill that acts on "the first of them" is how a replay goes
wrong without anyone noticing.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from browser_agent.browser.observation import SKIP_SUBTREE_ROLES, value_of

# Icon fonts put private-use characters into names (" SALES").
_PRIVATE_USE = re.compile("[-]")
_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_TABLE_ROLES = frozenset({"table", "grid", "treegrid"})
_CELL_ROLES = frozenset({"cell", "gridcell", "columnheader", "rowheader"})
# Fields say what they hold in their value, not in their name.
_VALUE_ROLES = frozenset({"textbox", "searchbox", "combobox", "spinbutton", "slider"})
_MAX_LISTED = 5


class LocatorError(RuntimeError):
    """A locator matched no element, or more than one."""


def normalize(text: str | None) -> str:
    """Text as it is compared: no icon glyphs, single spaces, no case, no required mark."""
    cleaned = re.sub(r"\s+", " ", _PRIVATE_USE.sub("", text or "")).strip()
    # A required field carries " *" after its label; a skill names the label.
    return cleaned.removesuffix("*").strip().casefold()


def fill(template: str, values: Mapping[str, Any]) -> str:
    """Replace {param} placeholders; a placeholder without a value is an error."""

    def put(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise LocatorError(f"no value for the placeholder {{{key}}} in {template!r}")
        return str(values[key])

    return _PLACEHOLDER.sub(put, template)


class Locator(BaseModel):
    """An element by role and accessible name, optionally inside a row or a section."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str
    name: str
    # Text that the table row holding the element shows, such as an order number. For
    # an element that is itself a row, the text it shows.
    row: str | None = None
    # Accessible name of an element that contains it, such as a form section or dialog.
    section: str | None = None

    @model_validator(mode="after")
    def _no_empty_parts(self) -> Locator:
        if not self.role.strip():
            raise ValueError("a locator needs a role")
        if self.row is not None and not self.row.strip():
            raise ValueError("row must hold some text, or be left out")
        if self.section is not None and not self.section.strip():
            raise ValueError("section must hold a name, or be left out")
        return self

    def filled(self, values: Mapping[str, Any]) -> Locator:
        """This locator with its {param} placeholders replaced."""
        return Locator(
            role=self.role,
            name=fill(self.name, values),
            row=None if self.row is None else fill(self.row, values),
            section=None if self.section is None else fill(self.section, values),
        )

    def describe(self) -> str:
        text = f'{self.role} "{self.name}"'
        if self.row is not None:
            text += f' in the row showing "{self.row}"'
        if self.section is not None:
            text += f' in the section "{self.section}"'
        return text


def _role(node: dict[str, Any]) -> str:
    return value_of(node.get("role")) or ""


class PageIndex:
    """The accessibility tree of one page, indexed for locators."""

    def __init__(self, nodes: list[dict[str, Any]]) -> None:
        self._by_id = {node["nodeId"]: node for node in nodes}
        self._parent = {
            child: node["nodeId"] for node in nodes for child in node.get("childIds", [])
        }
        self._nodes = [
            node
            for node in nodes
            if not node.get("ignored") and _role(node) not in SKIP_SUBTREE_ROLES
        ]

    # -- finding -----------------------------------------------------------

    def find(self, locator: Locator) -> list[dict[str, Any]]:
        """Every element the locator matches, one entry per element."""
        role, name = locator.role.strip().casefold(), normalize(locator.name)
        row = None if locator.row is None else normalize(locator.row)
        section = None if locator.section is None else normalize(locator.section)
        found: dict[int, dict[str, Any]] = {}
        for node in self._nodes:
            ref = node.get("backendDOMNodeId")
            if ref is None or _role(node).casefold() != role:
                continue
            if normalize(value_of(node.get("name"))) != name:
                continue
            ancestors = self._ancestors(node)
            # A row is located by its own text: "the row showing 000000230".
            if row is not None and not any(
                _role(up) == "row" and row in normalize(self.text(up)) for up in (node, *ancestors)
            ):
                continue
            if section is not None and not any(
                normalize(value_of(up.get("name"))) == section
                for up in ancestors
                if not up.get("ignored") and _role(up) != "StaticText"
            ):
                continue
            found.setdefault(ref, node)
        return list(found.values())

    def resolve(self, locator: Locator) -> dict[str, Any]:
        """The one element the locator matches; LocatorError when it is not exactly one."""
        found = self.find(locator)
        if len(found) == 1:
            return found[0]
        if not found:
            raise LocatorError(f"no element matches {locator.describe()}{self._near(locator)}")
        shown = "; ".join(self._where(node) for node in found[:_MAX_LISTED])
        more = "" if len(found) <= _MAX_LISTED else f"; and {len(found) - _MAX_LISTED} more"
        raise LocatorError(
            f"{len(found)} elements match {locator.describe()}, not one: {shown}{more}. "
            "Name the row or the section that holds the one meant"
        )

    def ref(self, locator: Locator) -> int:
        return int(self.resolve(locator)["backendDOMNodeId"])

    # -- reading -----------------------------------------------------------

    def text(self, node: dict[str, Any]) -> str:
        """What an element says: a field's value, else the text inside it, else its name."""
        if _role(node) in _VALUE_ROLES:
            value = value_of(node.get("value"))
            return "" if value is None else str(value).strip()
        parts = [
            (value_of(inner.get("name")) or "").strip()
            for inner in self._descendants(node)
            if _role(inner) == "StaticText"
        ]
        joined = re.sub(r"\s+", " ", " ".join(part for part in parts if part)).strip()
        return joined or re.sub(r"\s+", " ", value_of(node.get("name")) or "").strip()

    def table(self, node: dict[str, Any]) -> list[list[str]]:
        """The rows of a table as lists of cell texts, header row included."""
        rows = []
        for inner in self._descendants(node):
            if _role(inner) != "row" or self._table_of(inner) is not node:
                continue
            cells = [cell for cell in self._descendants(inner) if _role(cell) in _CELL_ROLES]
            rows.append([self.text(cell) for cell in cells if self._row_of(cell) is inner])
        return rows

    def is_table(self, node: dict[str, Any]) -> bool:
        return _role(node) in _TABLE_ROLES

    def has_text(self, text: str) -> bool:
        """Whether the page shows this text anywhere, in an element's name or value."""
        wanted = normalize(text)
        if not wanted:
            return False
        for node in self._nodes:
            if wanted in normalize(value_of(node.get("name"))):
                return True
            value = value_of(node.get("value"))
            if value is not None and wanted in normalize(str(value)):
                return True
        return False

    # -- internals ---------------------------------------------------------

    def _ancestors(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        found = []
        current = self._parent.get(node["nodeId"])
        while current is not None:
            parent = self._by_id.get(current)
            if parent is None:
                break
            found.append(parent)
            current = self._parent.get(current)
        return found

    def _descendants(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        """Everything under a node, in document order, without ignored wrappers."""
        found = []
        stack = list(reversed(node.get("childIds", [])))
        while stack:
            current = self._by_id.get(stack.pop())
            if current is None or _role(current) in SKIP_SUBTREE_ROLES:
                continue
            if not current.get("ignored"):
                found.append(current)
            stack.extend(reversed(current.get("childIds", [])))
        return found

    def _nearest(self, node: dict[str, Any], roles: frozenset[str]) -> dict[str, Any] | None:
        return next((up for up in self._ancestors(node) if _role(up) in roles), None)

    def _table_of(self, node: dict[str, Any]) -> dict[str, Any] | None:
        return self._nearest(node, _TABLE_ROLES)

    def _row_of(self, node: dict[str, Any]) -> dict[str, Any] | None:
        return self._nearest(node, frozenset({"row"}))

    def _where(self, node: dict[str, Any]) -> str:
        """One match in words, with the row it is in, so a locator can be narrowed."""
        row = node if _role(node) == "row" else self._row_of(node)
        if row is not None:
            return f'one in the row "{self.text(row)[:60]}"'
        section = next(
            (
                (value_of(up.get("name")) or "").strip()
                for up in self._ancestors(node)
                if not up.get("ignored")
                and _role(up) not in ("StaticText", "RootWebArea")
                and (value_of(up.get("name")) or "").strip()
            ),
            None,
        )
        return f'one in the section "{section[:60]}"' if section else "one outside any section"

    def _near(self, locator: Locator) -> str:
        """What comes closest to a locator that matched nothing, for the error message."""
        role, name = locator.role.strip().casefold(), normalize(locator.name)
        same_name = sorted(
            {
                _role(node)
                for node in self._nodes
                if "backendDOMNodeId" in node
                and normalize(value_of(node.get("name"))) == name
                and _role(node) != "StaticText"
            }
        )
        if locator.row is None and locator.section is None and same_name:
            return f'; an element named "{locator.name}" exists with role {", ".join(same_name)}'
        without = Locator(role=locator.role, name=locator.name)
        if (locator.row or locator.section) and self.find(without):
            return f"; {without.describe()} exists, but not in that row or section"
        names = sorted(
            {
                (value_of(node.get("name")) or "").strip()
                for node in self._nodes
                if _role(node).casefold() == role and value_of(node.get("name"))
            }
        )
        if names:
            listed = ", ".join(f'"{item}"' for item in names[:8])
            return f"; elements with role {locator.role} are named {listed}"
        return ""
