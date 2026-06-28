"""Lightweight per-call telemetry stored in a local SQLite file.

What we record per tool call:
    * timestamp (UTC, ISO-8601)
    * tool name
    * duration in milliseconds
    * status: "ok" if the function returned, "error" if it raised
    * error message (type + str), only when status == "error"

We intentionally do NOT record arguments or return values to avoid leaking
secrets (tokens, passwords, hashed inputs, etc.) into the telemetry DB.

Toggle via env var ``MCP_TELEMETRY=0`` to disable; override the DB path with
``MCP_TELEMETRY_DB``.
"""

from __future__ import annotations

import datetime
import functools
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("mcp.telemetry")

TELEMETRY_DB_PATH = os.environ.get("MCP_TELEMETRY_DB", "data/telemetry.db")
_ENABLED = os.environ.get("MCP_TELEMETRY", "1") != "0"


def _percentile(sorted_values: list[float], p: float) -> float:
    """Linear-interpolation percentile from a pre-sorted list. 0 for empty input."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return round(float(sorted_values[0]), 3)
    k = (len(sorted_values) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = k - lo
    val = sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac
    return round(float(val), 3)


class TelemetryDB:
    """Thread-safe SQLite-backed store of tool-call telemetry."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS tool_calls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        tool TEXT NOT NULL,
        duration_ms REAL NOT NULL,
        status TEXT NOT NULL,
        error TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_tool_calls_ts ON tool_calls(ts DESC);
    CREATE INDEX IF NOT EXISTS idx_tool_calls_tool ON tool_calls(tool);
    """

    def __init__(self, path: str) -> None:
        self.path = path
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(self._SCHEMA)
            self._conn.commit()

    def record(self, tool: str, duration_ms: float, status: str, error: str | None = None) -> None:
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO tool_calls (ts, tool, duration_ms, status, error) VALUES (?, ?, ?, ?, ?)",
                (ts, tool, duration_ms, status, error),
            )
            self._conn.commit()

    def recent(self, limit: int = 100, tool: str | None = None, status: str | None = None) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if tool:
            clauses.append("tool = ?")
            params.append(tool)
        if status:
            clauses.append("status = ?")
            params.append(status)
        sql = "SELECT id, ts, tool, duration_ms, status, error FROM tool_calls"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(int(limit))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def summary(self, since_minutes: int = 60) -> dict:
        cutoff = (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(minutes=since_minutes)
        ).isoformat()
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS errors,
                    AVG(duration_ms) AS avg_ms,
                    MIN(duration_ms) AS min_ms,
                    MAX(duration_ms) AS max_ms
                FROM tool_calls WHERE ts >= ?
                """,
                (cutoff,),
            ).fetchone()
            # Pull all durations to compute percentiles in Python — SQLite
            # has no PERCENTILE_CONT and the row count is small enough that
            # one sorted pass is cheaper than the round trips would be.
            durations = [
                r[0] for r in self._conn.execute(
                    "SELECT duration_ms FROM tool_calls WHERE ts >= ? ORDER BY duration_ms",
                    (cutoff,),
                ).fetchall()
            ]
        out = dict(row) if row else {}
        # SQLite returns None for SUM/AVG on empty sets — normalize to 0.
        for k in ("total", "errors"):
            if out.get(k) is None:
                out[k] = 0
        for k in ("avg_ms", "min_ms", "max_ms"):
            if out.get(k) is None:
                out[k] = 0.0
            else:
                out[k] = round(float(out[k]), 3)
        out["p50_ms"] = _percentile(durations, 50)
        out["p95_ms"] = _percentile(durations, 95)
        out["p99_ms"] = _percentile(durations, 99)
        out["since_minutes"] = since_minutes
        return out

    def slowest(self, limit: int = 10, since_minutes: int = 1440) -> list[dict]:
        cutoff = (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(minutes=since_minutes)
        ).isoformat()
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, ts, tool, duration_ms, status, error
                FROM tool_calls WHERE ts >= ?
                ORDER BY duration_ms DESC LIMIT ?
                """,
                (cutoff, int(limit)),
            ).fetchall()
        return [dict(r) for r in rows]

    def recent_errors(self, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, ts, tool, duration_ms, error
                FROM tool_calls WHERE status = 'error'
                ORDER BY id DESC LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [dict(r) for r in rows]

    def per_tool_counts(self, since_minutes: int = 1440) -> list[dict]:
        cutoff = (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(minutes=since_minutes)
        ).isoformat()
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT tool,
                       COUNT(*) AS calls,
                       SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS errors,
                       AVG(duration_ms) AS avg_ms
                FROM tool_calls WHERE ts >= ?
                GROUP BY tool ORDER BY calls DESC
                """,
                (cutoff,),
            ).fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0])

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM tool_calls")
            self._conn.commit()


# Module-level singleton — created lazily so import is cheap and tests can swap it.
_db: TelemetryDB | None = None


def get_db() -> TelemetryDB:
    global _db
    if _db is None:
        _db = TelemetryDB(TELEMETRY_DB_PATH)
    return _db


def set_db(db: TelemetryDB | None) -> None:
    """Test hook: replace (or reset to None) the singleton."""
    global _db
    _db = db


def is_enabled() -> bool:
    return _ENABLED


def set_enabled(enabled: bool) -> None:
    global _ENABLED
    _ENABLED = enabled


def traced(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: record one telemetry row per call.

    On exception, the row's status is ``"error"`` and the exception is re-raised
    unchanged. Tool-level failures returned as ``{"error": ...}`` dicts count as
    ``"ok"`` (that's a normal return, not a server fault).
    """
    name = fn.__name__

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not is_enabled():
            return fn(*args, **kwargs)
        start = time.perf_counter()
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            duration_ms = (time.perf_counter() - start) * 1000
            try:
                get_db().record(name, duration_ms, "error", error=f"{type(exc).__name__}: {exc}")
            except Exception:  # noqa: BLE001
                logger.exception("failed to write telemetry row")
            raise
        duration_ms = (time.perf_counter() - start) * 1000
        try:
            get_db().record(name, duration_ms, "ok")
        except Exception:  # noqa: BLE001
            logger.exception("failed to write telemetry row")
        return result

    return wrapper
