"""Append-only observation lineage with explicit provenance and bidirectional links.

This models *records of interactions*, not model weights, consciousness, or
an assertion that a recorded explanation captures hidden causal processes.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

KINDS = frozenset({"observation", "inference", "revision"})


@dataclass(frozen=True)
class Record:
    event_id: str
    occurred_at: str  # ISO 8601 with explicit timezone offset
    kind: str
    actor: str
    statement: str
    parent_ids: tuple[str, ...] = ()
    source_ref: str | None = None


class TraceStore:
    """SQLite-backed, append-only DAG of attributed records.

    Every observation names a source; later inferences and revisions must link
    to existing earlier records. Source identifiers are declarations, not
    independent verification of authenticity or causal correctness.
    """

    def __init__(self, path: str | Path):
        self._db = sqlite3.connect(str(path))
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS records (
                event_id TEXT PRIMARY KEY,
                occurred_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                actor TEXT NOT NULL,
                statement TEXT NOT NULL,
                source_ref TEXT
            );
            CREATE TABLE IF NOT EXISTS parents (
                event_id TEXT NOT NULL REFERENCES records(event_id),
                parent_id TEXT NOT NULL REFERENCES records(event_id),
                ordinal INTEGER NOT NULL,
                PRIMARY KEY(event_id, parent_id),
                UNIQUE(event_id, ordinal)
            );
            CREATE INDEX IF NOT EXISTS parents_by_parent ON parents(parent_id);
        """)

    def close(self) -> None:
        self._db.close()

    @staticmethod
    def _instant(value: str) -> datetime:
        try:
            dt = datetime.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("occurred_at must be an ISO 8601 timestamp") from exc
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone offset")
        return dt.astimezone(timezone.utc)

    def add(self, record: Record) -> None:
        if not all((record.event_id, record.actor, record.statement)):
            raise ValueError("event_id, actor, and statement are required")
        if record.kind not in KINDS:
            raise ValueError(f"unknown record kind: {record.kind}")
        instant = self._instant(record.occurred_at)
        parents = tuple(record.parent_ids)
        if len(parents) != len(set(parents)):
            raise ValueError("duplicate parent references")
        if record.event_id in parents:
            raise ValueError("record cannot be its own parent")
        if record.kind == "observation":
            if not record.source_ref:
                raise ValueError("observations require a source_ref")
        else:
            if not parents:
                raise ValueError("inferences and revisions require a parent")
            if record.source_ref is not None:
                raise ValueError("derived records inherit evidence through parents")
        with self._db:
            for parent_id in parents:
                parent = self.get(parent_id)  # Raises KeyError for missing ancestry.
                if self._instant(parent.occurred_at) > instant:
                    raise ValueError("a parent cannot occur after its child")
            self._db.execute(
                "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?)",
                (record.event_id, record.occurred_at, record.kind,
                 record.actor, record.statement, record.source_ref),
            )
            self._db.executemany(
                "INSERT INTO parents VALUES (?, ?, ?)",
                [(record.event_id, parent, i) for i, parent in enumerate(parents)],
            )

    def get(self, event_id: str) -> Record:
        row = self._db.execute(
            "SELECT event_id, occurred_at, kind, actor, statement, source_ref "
            "FROM records WHERE event_id=?", (event_id,)
        ).fetchone()
        if row is None:
            raise KeyError(event_id)
        parents = tuple(p[0] for p in self._db.execute(
            "SELECT parent_id FROM parents WHERE event_id=? ORDER BY ordinal",
            (event_id,),
        ))
        return Record(row[0], row[1], row[2], row[3], row[4], parents, row[5])

    def ancestors(self, event_id: str) -> list[Record]:
        """All ancestors in dependency-first order; excludes the starting record."""
        self.get(event_id)
        visited: set[str] = set()
        ordered: list[Record] = []

        def visit(node_id: str) -> None:
            for parent_id in self.get(node_id).parent_ids:
                if parent_id not in visited:
                    visited.add(parent_id)
                    visit(parent_id)
                    ordered.append(self.get(parent_id))

        visit(event_id)
        return ordered

    def descendants(self, event_id: str) -> list[Record]:
        """Forward links ordered by timestamp, excluding the starting record."""
        self.get(event_id)
        visited = {event_id}
        pending = [event_id]
        children: list[Record] = []
        while pending:
            node_id = pending.pop(0)
            for (child_id,) in self._db.execute(
                "SELECT event_id FROM parents WHERE parent_id=? ORDER BY event_id",
                (node_id,),
            ):
                if child_id not in visited:
                    visited.add(child_id)
                    pending.append(child_id)
                    children.append(self.get(child_id))
        return sorted(children, key=lambda r: (self._instant(r.occurred_at), r.event_id))

    def independent_source_refs(self, event_id: str) -> frozenset[str]:
        """Deduplicate *declared* evidence sources, not repeated retellings.

        A source ID must be assigned consistently by the caller; this method
        cannot prove source independence or truth.
        """
        lineage = [*self.ancestors(event_id), self.get(event_id)]
        return frozenset(
            r.source_ref for r in lineage
            if r.kind == "observation" and r.source_ref is not None
        )
