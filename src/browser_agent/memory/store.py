"""One memory build on disk: skills, site facts and lessons, with their versions.

A build is a directory, memory_store/<date>_<name>/:

    provenance.json   which runs and tasks it was built from, with which models and code
    manifest.json     every item and version, its status and a hash of its content
    memory.sqlite     site facts, lessons and the metadata of every item
    skills/<name>/v<N>/SKILL.md [+ skill.py]

Memory is append-only. An update is a new version; the version before it is marked
retired and stays where it is. Nothing is overwritten or deleted. A run opens a build
read-only, so a test run cannot change what it is measured with.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from browser_agent.memory.skill import Skill, load_skill, write_skill

Kind = Literal["skill", "site_fact", "lesson"]
ACTIVE, RETIRED = "active", "retired"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    kind TEXT NOT NULL,
    id TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL,
    created TEXT NOT NULL,
    url_pattern TEXT NOT NULL,
    text TEXT NOT NULL,
    source TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    use_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (kind, id, version)
)
"""


class StoreError(RuntimeError):
    """The store was asked to do something that would break append-only memory."""


@dataclass(frozen=True)
class Item:
    """One version of one memory item."""

    kind: str
    id: str
    version: int
    status: str
    created: str
    url_pattern: str
    # A fact or a lesson in full; for a skill, its one-line description.
    text: str
    source: Any
    note: str = ""
    use_count: int = 0
    success_count: int = 0

    @property
    def label(self) -> str:
        return f"{self.id}@v{self.version}"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class MemoryStore:
    """A memory build. Open it with create() to build, with open() to use it."""

    def __init__(self, root: Path, connection: sqlite3.Connection, read_only: bool) -> None:
        self.root = root
        self._db = connection
        self._read_only = read_only

    @classmethod
    def create(cls, root: Path, provenance: dict[str, Any]) -> MemoryStore:
        """Start a new build in a directory that does not exist yet."""
        if root.exists():
            raise StoreError(f"{root} exists; a new build gets a new directory")
        root.mkdir(parents=True)
        (root / "provenance.json").write_text(
            json.dumps({"created": _now(), **provenance}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        connection = sqlite3.connect(root / "memory.sqlite")
        connection.execute(_SCHEMA)
        connection.commit()
        return cls(root, connection, read_only=False)

    @classmethod
    def open(cls, root: Path, read_only: bool = True) -> MemoryStore:
        """Open an existing build; read-only unless a build step continues it."""
        database = root / "memory.sqlite"
        if not database.is_file():
            raise StoreError(f"{root} is not a memory build")
        if read_only:
            connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
        else:
            connection = sqlite3.connect(database)
        return cls(root, connection, read_only)

    def close(self) -> None:
        self._db.close()

    def provenance(self) -> dict[str, Any]:
        return json.loads((self.root / "provenance.json").read_text(encoding="utf-8"))

    # -- reading -----------------------------------------------------------

    def items(self, kind: Kind | None = None, active_only: bool = True) -> list[Item]:
        """Item versions in the order they were added."""
        query = (
            "SELECT kind, id, version, status, created, url_pattern, text, source, note, "
            "use_count, success_count FROM items"
        )
        clauses, values = [], []
        if kind is not None:
            clauses.append("kind = ?")
            values.append(kind)
        if active_only:
            clauses.append("status = ?")
            values.append(ACTIVE)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        rows = self._db.execute(query + " ORDER BY rowid", values).fetchall()
        return [Item(*row[:7], json.loads(row[7]), *row[8:]) for row in rows]

    def skills(self) -> dict[str, Skill]:
        """The active version of every skill, by name."""
        return {
            item.id: load_skill(self.skill_dir(item.id, item.version))
            for item in self.items("skill")
        }

    def skill_dir(self, name: str, version: int) -> Path:
        return self.root / "skills" / name / f"v{version}"

    # -- writing -----------------------------------------------------------

    def add(
        self,
        kind: Kind,
        item_id: str,
        text: str,
        url_pattern: str,
        source: Any,
        note: str = "",
    ) -> Item:
        """Add a new item, or a new version of one; the version before it is retired."""
        self._writable()
        latest = self._db.execute(
            "SELECT MAX(version) FROM items WHERE kind = ? AND id = ?", (kind, item_id)
        ).fetchone()[0]
        version = (latest or 0) + 1
        if latest is not None:
            self._db.execute(
                "UPDATE items SET status = ?, note = note || ? "
                "WHERE kind = ? AND id = ? AND status = ?",
                (RETIRED, f" [superseded by v{version}]", kind, item_id, ACTIVE),
            )
        item = Item(kind, item_id, version, ACTIVE, _now(), url_pattern, text, source, note)
        self._db.execute(
            "INSERT INTO items (kind, id, version, status, created, url_pattern, text, source, "
            "note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, item_id, version, ACTIVE, item.created, url_pattern, text,
             json.dumps(source, ensure_ascii=False), note),
        )  # fmt: skip
        self._db.commit()
        return item

    def add_skill(self, skill: Skill, source: Any, note: str = "") -> Item:
        """Add a skill version; its files go into a folder of their own."""
        self._writable()
        latest = self._db.execute(
            "SELECT MAX(version) FROM items WHERE kind = 'skill' AND id = ?", (skill.name,)
        ).fetchone()[0]
        if skill.meta.version != (latest or 0) + 1:
            raise StoreError(
                f"{skill.name} is at version {latest or 0}; the next version is "
                f"{(latest or 0) + 1}, not {skill.meta.version}"
            )
        write_skill(self.skill_dir(skill.name, skill.meta.version), skill)
        return self.add(
            "skill", skill.name, skill.meta.description, skill.meta.url_pattern, source, note
        )

    def retire(self, kind: Kind, item_id: str, reason: str) -> None:
        """Mark the active version of an item as retired. It stays in the store."""
        self._writable()
        changed = self._db.execute(
            "UPDATE items SET status = ?, note = note || ? "
            "WHERE kind = ? AND id = ? AND status = ?",
            (RETIRED, f" [retired: {reason}]", kind, item_id, ACTIVE),
        ).rowcount
        if not changed:
            raise StoreError(f"no active {kind} {item_id} to retire")
        self._db.commit()

    def count_use(self, kind: Kind, item_id: str, version: int, success: bool) -> None:
        """Count one use of an item version. Only while building: runs are read-only."""
        self._writable()
        self._db.execute(
            "UPDATE items SET use_count = use_count + 1, success_count = success_count + ? "
            "WHERE kind = ? AND id = ? AND version = ?",
            (int(success), kind, item_id, version),
        )
        self._db.commit()

    def write_manifest(self) -> dict[str, Any]:
        """Write manifest.json: every item version with its status and content hash."""
        self._writable()
        entries = []
        for item in self.items(active_only=False):
            content = item.text
            files = []
            if item.kind == "skill":
                folder = self.skill_dir(item.id, item.version)
                files = sorted(path.name for path in folder.iterdir())
                content = "".join(
                    (folder / name).read_text(encoding="utf-8").replace("\r\n", "\n")
                    for name in files
                )
            entry = {
                "kind": item.kind,
                "id": item.id,
                "version": item.version,
                "status": item.status,
                "created": item.created,
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            }
            if files:
                entry["files"] = files
            entries.append(entry)
        manifest = {"written": _now(), "items": entries}
        (self.root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    def _writable(self) -> None:
        if self._read_only:
            raise StoreError("this memory build is open read-only; memory is frozen during runs")
