"""Tiny SQLite-backed notes store used by the MCP notes tools.

A single-table store with id/title/body/timestamps. Kept separate from the
server module so it's easy to unit test.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT    NOT NULL,
    body       TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_updated_at ON notes(updated_at DESC);
"""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class NotesDB:
    """Thread-safe wrapper around a SQLite notes table."""

    def __init__(self, path: str | Path = "notes.db") -> None:
        self.path = str(path)
        parent = Path(self.path).resolve().parent
        parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "title": row["title"],
            "body": row["body"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def add(self, title: str, body: str = "") -> dict:
        if not title or not title.strip():
            raise ValueError("title must not be empty")
        now = _utcnow_iso()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO notes (title, body, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (title.strip(), body, now, now),
            )
            conn.commit()
            note_id = cur.lastrowid
            row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return self._row_to_dict(row)

    def get(self, note_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM notes WHERE id = ?", (int(note_id),)).fetchone()
        return self._row_to_dict(row) if row else None

    def list(self, limit: int = 50, search: str | None = None) -> list[dict]:
        limit = max(1, min(int(limit), 500))
        with self._connect() as conn:
            if search:
                like = f"%{search}%"
                rows = conn.execute(
                    "SELECT * FROM notes WHERE title LIKE ? OR body LIKE ? "
                    "ORDER BY updated_at DESC, id DESC LIMIT ?",
                    (like, like, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM notes ORDER BY updated_at DESC, id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update(self, note_id: int, title: str | None = None, body: str | None = None) -> dict | None:
        if title is None and body is None:
            raise ValueError("at least one of title or body must be provided")
        if title is not None and not title.strip():
            raise ValueError("title must not be empty")
        with self._lock, self._connect() as conn:
            existing = conn.execute("SELECT * FROM notes WHERE id = ?", (int(note_id),)).fetchone()
            if not existing:
                return None
            new_title = title.strip() if title is not None else existing["title"]
            new_body = body if body is not None else existing["body"]
            conn.execute(
                "UPDATE notes SET title = ?, body = ?, updated_at = ? WHERE id = ?",
                (new_title, new_body, _utcnow_iso(), int(note_id)),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM notes WHERE id = ?", (int(note_id),)).fetchone()
        return self._row_to_dict(row)

    def delete(self, note_id: int) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM notes WHERE id = ?", (int(note_id),))
            conn.commit()
        return cur.rowcount > 0

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM notes").fetchone()
        return int(row["c"])
