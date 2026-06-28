"""Tests for server/telemetry.py and the @traced decorator."""

from __future__ import annotations

import os
import pytest

from server import telemetry


@pytest.fixture
def db(tmp_path):
    """Fresh TelemetryDB pointed at a temp file, installed as the singleton."""
    db = telemetry.TelemetryDB(str(tmp_path / "telemetry.db"))
    telemetry.set_db(db)
    telemetry.set_enabled(True)
    try:
        yield db
    finally:
        telemetry.set_db(None)
        telemetry.set_enabled(True)


class TestTelemetryDB:
    def test_record_and_recent(self, db):
        db.record("calculate", 1.2, "ok")
        db.record("fetch_url", 42.5, "error", error="ValueError: nope")
        rows = db.recent()
        assert len(rows) == 2
        assert rows[0]["tool"] == "fetch_url"
        assert rows[0]["status"] == "error"
        assert rows[0]["error"] == "ValueError: nope"
        assert rows[1]["tool"] == "calculate"
        assert rows[1]["error"] is None

    def test_recent_filter_by_tool(self, db):
        db.record("a", 1.0, "ok")
        db.record("b", 1.0, "ok")
        db.record("a", 1.0, "ok")
        assert len(db.recent(tool="a")) == 2
        assert len(db.recent(tool="b")) == 1

    def test_recent_filter_by_status(self, db):
        db.record("a", 1.0, "ok")
        db.record("a", 1.0, "error", error="x")
        assert len(db.recent(status="error")) == 1
        assert len(db.recent(status="ok")) == 1

    def test_summary_empty(self, db):
        s = db.summary()
        assert s["total"] == 0
        assert s["errors"] == 0
        assert s["avg_ms"] == 0.0

    def test_summary_with_rows(self, db):
        db.record("a", 10.0, "ok")
        db.record("a", 20.0, "ok")
        db.record("b", 30.0, "error", error="boom")
        s = db.summary()
        assert s["total"] == 3
        assert s["errors"] == 1
        assert s["avg_ms"] == 20.0
        assert s["min_ms"] == 10.0
        assert s["max_ms"] == 30.0

    def test_per_tool_counts(self, db):
        db.record("a", 1.0, "ok")
        db.record("a", 2.0, "ok")
        db.record("b", 3.0, "error", error="x")
        rows = db.per_tool_counts()
        by_tool = {r["tool"]: r for r in rows}
        assert by_tool["a"]["calls"] == 2
        assert by_tool["a"]["errors"] == 0
        assert by_tool["b"]["calls"] == 1
        assert by_tool["b"]["errors"] == 1

    def test_clear(self, db):
        db.record("a", 1.0, "ok")
        db.clear()
        assert db.count() == 0

    def test_summary_includes_percentiles(self, db):
        # 100 values 1..100 → p50=50.5, p95~95.05, p99~99.01
        for i in range(1, 101):
            db.record("a", float(i), "ok")
        s = db.summary()
        assert s["total"] == 100
        assert 50.0 <= s["p50_ms"] <= 51.0
        assert 94.0 <= s["p95_ms"] <= 96.0
        assert 98.0 <= s["p99_ms"] <= 100.0
        assert s["min_ms"] == 1.0
        assert s["max_ms"] == 100.0

    def test_summary_percentiles_empty(self, db):
        s = db.summary()
        assert s["p50_ms"] == 0.0
        assert s["p95_ms"] == 0.0
        assert s["p99_ms"] == 0.0

    def test_slowest(self, db):
        db.record("fast", 1.0, "ok")
        db.record("medium", 5.0, "ok")
        db.record("slow", 99.0, "ok")
        db.record("also_slow", 50.0, "error", error="x")
        rows = db.slowest(limit=2)
        assert len(rows) == 2
        assert rows[0]["tool"] == "slow"
        assert rows[0]["duration_ms"] == 99.0
        assert rows[1]["tool"] == "also_slow"

    def test_recent_errors_only(self, db):
        db.record("a", 1.0, "ok")
        db.record("b", 2.0, "error", error="boom")
        db.record("c", 3.0, "error", error="kaboom")
        rows = db.recent_errors()
        assert len(rows) == 2
        assert {r["tool"] for r in rows} == {"b", "c"}
        assert all("error" in r and r["error"] for r in rows)


class TestTracedDecorator:
    def test_success_records_ok(self, db):
        @telemetry.traced
        def add(a, b):
            return a + b

        assert add(2, 3) == 5
        rows = db.recent()
        assert len(rows) == 1
        assert rows[0]["tool"] == "add"
        assert rows[0]["status"] == "ok"
        assert rows[0]["error"] is None
        assert rows[0]["duration_ms"] >= 0

    def test_exception_records_error_and_reraises(self, db):
        @telemetry.traced
        def boom():
            raise ValueError("nope")

        with pytest.raises(ValueError, match="nope"):
            boom()
        rows = db.recent()
        assert len(rows) == 1
        assert rows[0]["status"] == "error"
        assert "ValueError" in rows[0]["error"]
        assert "nope" in rows[0]["error"]

    def test_disabled_is_noop(self, db):
        telemetry.set_enabled(False)

        @telemetry.traced
        def add(a, b):
            return a + b

        assert add(1, 2) == 3
        assert db.count() == 0

    def test_app_level_error_dict_counts_as_ok(self, db):
        """Tools returning {'error': ...} should NOT pollute the error rate."""

        @telemetry.traced
        def soft_fail():
            return {"error": "bad input"}

        result = soft_fail()
        assert result == {"error": "bad input"}
        rows = db.recent()
        assert rows[0]["status"] == "ok"

    def test_preserves_signature(self, db):
        @telemetry.traced
        def documented(x: int) -> int:
            """Doc string."""
            return x

        assert documented.__name__ == "documented"
        assert documented.__doc__ == "Doc string."


class TestEnvOverrides:
    def test_db_path_env_var(self, tmp_path, monkeypatch):
        custom = tmp_path / "custom.db"
        monkeypatch.setenv("MCP_TELEMETRY_DB", str(custom))
        # Re-import to pick up env var
        import importlib

        import server.telemetry as t

        telemetry.set_db(None)
        importlib.reload(t)
        try:
            db = t.get_db()
            assert db.path == str(custom)
            assert os.path.exists(custom)
        finally:
            t.set_db(None)
