"""Tests for the safety helpers and the hardened tools.

These tests focus on the *abuse cases* that previously hung the server or
exposed it to SSRF: huge exponents, private/loopback URLs, and catastrophic
regex backtracking.
"""

from __future__ import annotations

import importlib
import os
import time

import pytest

from server.safety import (
    MathError,
    TimeoutExceeded,
    check_url_is_public,
    run_with_timeout,
    safe_eval_math,
)


# --- safe_eval_math --------------------------------------------------------

class TestSafeEvalMath:
    def test_basic(self):
        assert safe_eval_math("2 + 2 * 10") == 22
        assert safe_eval_math("(1 + 2) * 3") == 9
        assert safe_eval_math("-5 + 7") == 2
        assert safe_eval_math("10 / 4") == 2.5
        assert safe_eval_math("10 // 3") == 3
        assert safe_eval_math("10 % 3") == 1
        assert safe_eval_math("2 ** 10") == 1024
        assert safe_eval_math("3.14 * 2") == pytest.approx(6.28)

    def test_rejects_giant_exponent(self):
        with pytest.raises(MathError):
            safe_eval_math("9 ** 9999")

    def test_rejects_names_and_calls(self):
        for expr in [
            "__import__('os')",
            "open('x')",
            "x + 1",
            "abs(-3)",
            "1 if True else 0",
            "[1,2,3]",
        ]:
            with pytest.raises(MathError):
                safe_eval_math(expr)

    def test_rejects_too_long(self):
        with pytest.raises(MathError):
            safe_eval_math("1 + " * 100 + "1")  # well over 200 chars

    def test_rejects_garbage(self):
        with pytest.raises(MathError):
            safe_eval_math("this is not math")


# --- SSRF check -----------------------------------------------------------

class TestCheckUrlIsPublic:
    @pytest.mark.parametrize("url", [
        "http://localhost/",
        "http://127.0.0.1/",
        "http://127.1.2.3/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",  # AWS metadata
        "http://[::1]/",
    ])
    def test_blocks_private(self, url):
        with pytest.raises(ValueError):
            check_url_is_public(url)

    @pytest.mark.parametrize("url", [
        "ftp://example.com/",
        "file:///etc/passwd",
        "gopher://x/",
        "",
        "not a url",
        "http:///nohost",
    ])
    def test_blocks_bad_schemes_and_shapes(self, url):
        with pytest.raises(ValueError):
            check_url_is_public(url)

    def test_allows_public(self):
        # example.com is reserved-public; this should succeed unless the host has no DNS.
        try:
            check_url_is_public("https://example.com/")
        except ValueError as e:
            pytest.skip(f"DNS not available in this env: {e}")


# --- run_with_timeout -----------------------------------------------------

class TestRunWithTimeout:
    def test_completes(self):
        assert run_with_timeout(lambda: 42, timeout=1.0) == 42

    def test_times_out(self):
        start = time.perf_counter()
        with pytest.raises(TimeoutExceeded):
            run_with_timeout(lambda: time.sleep(5), timeout=0.2)
        assert time.perf_counter() - start < 2.0


# --- Hardened tools (via the server module) -------------------------------

@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    os.environ["MCP_NOTES_DB"] = str(tmp_path_factory.mktemp("safety") / "notes.db")
    for mod in ("server.app", "server"):
        if mod in importlib.sys.modules:
            del importlib.sys.modules[mod]
    return importlib.import_module("server.app")


class TestCalculateTool:
    def test_normal(self, srv):
        assert srv.calculate("2 + 2 * 10") == "2 + 2 * 10 = 22"

    def test_blocks_giant_exponent(self, srv):
        out = srv.calculate("9 ** 9999")
        assert "Error" in out and "exponent" in out

    def test_blocks_names(self, srv):
        out = srv.calculate("__import__('os').system('echo pwned')")
        assert out.startswith("Error")


class TestRegexMatchTool:
    def test_normal(self, srv):
        out = srv.regex_match(r"\d+", "abc 12 def 345")
        assert out["count"] == 2

    def test_text_too_long(self, srv):
        out = srv.regex_match(r"x", "x" * 2_000_000)
        assert "error" in out and "too long" in out["error"]

    def test_pattern_too_long(self, srv):
        out = srv.regex_match("a" * 2000, "abc")
        assert "error" in out and "too long" in out["error"]


class TestFetchUrlTool:
    @pytest.mark.parametrize("url", [
        "http://127.0.0.1/",
        "http://169.254.169.254/",
        "ftp://example.com/",
    ])
    def test_blocks_ssrf_and_bad_schemes(self, srv, url):
        out = srv.fetch_url(url)
        assert "error" in out, out


class TestNoteValidation:
    def test_long_title_rejected(self, srv):
        out = srv.note_add("x" * 1000)
        assert "error" in out and "title" in out["error"]

    def test_long_body_rejected(self, srv):
        out = srv.note_add("ok", "x" * 200_000)
        assert "error" in out and "body" in out["error"]
