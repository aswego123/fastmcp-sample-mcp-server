"""Unit tests for the pure / non-network tool functions in the server.

Imports the package normally now that the project is a proper package layout.
Network tools (fetch_url, weather) are excluded — see clients/cli.py smoke
command for those.
"""

from __future__ import annotations

import importlib
import os

import pytest


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    # Point the server at a throwaway notes DB so importing it doesn't touch the real one.
    os.environ["MCP_NOTES_DB"] = str(tmp_path_factory.mktemp("srv") / "notes.db")
    # Force a fresh import so the env var is picked up.
    if "server.app" in importlib.sys.modules:
        del importlib.sys.modules["server.app"]
    if "server" in importlib.sys.modules:
        del importlib.sys.modules["server"]
    module = importlib.import_module("server.app")
    return module


# --- encoding / hashing ---------------------------------------------------

def test_hash_text(srv):
    out = srv.hash_text("hello", "sha256")
    assert out["algorithm"] == "sha256"
    assert out["hex"] == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def test_hash_text_unknown_algo(srv):
    out = srv.hash_text("x", "blake7")
    assert "error" in out


def test_base64_roundtrip(srv):
    encoded = srv.base64_encode("hello world")
    assert srv.base64_decode(encoded) == "hello world"


def test_base64_decode_invalid(srv):
    assert srv.base64_decode("!!!notb64!!!").startswith("Error")


# --- identifiers / secrets -------------------------------------------------

def test_uuid_generate(srv):
    out = srv.uuid_generate(count=3)
    assert out["count"] == 3
    assert len(out["uuids"]) == 3
    assert len(set(out["uuids"])) == 3


def test_uuid_bounds(srv):
    assert "error" in srv.uuid_generate(count=0)
    assert "error" in srv.uuid_generate(count=101)
    assert "error" in srv.uuid_generate(version=7)


def test_password_generate_length_and_charset(srv):
    out = srv.password_generate(length=32, use_uppercase=True, use_digits=True, use_symbols=True)
    pwd = out["password"]
    assert out["length"] == 32 == len(pwd)
    assert any(c.islower() for c in pwd)
    assert any(c.isupper() for c in pwd)
    assert any(c.isdigit() for c in pwd)


def test_password_bounds(srv):
    assert "error" in srv.password_generate(length=4)
    assert "error" in srv.password_generate(length=200)


# --- json / regex ----------------------------------------------------------

def test_json_format_ok(srv):
    out = srv.json_format('{"b":2,"a":1}', indent=2, sort_keys=True)
    assert out.startswith("{")
    assert '"a"' in out and out.index('"a"') < out.index('"b"')


def test_json_format_invalid(srv):
    assert srv.json_format("{not json").startswith("Error")


def test_regex_match(srv):
    out = srv.regex_match(r"\d+", "abc 12 def 345")
    assert out["count"] == 2
    assert [m["match"] for m in out["matches"]] == ["12", "345"]


def test_regex_invalid(srv):
    assert "error" in srv.regex_match("(unclosed", "x")


# --- conversions -----------------------------------------------------------

def test_convert_length(srv):
    out = srv.convert_units(1, "km", "m")
    assert out["result"] == 1000.0


def test_convert_temperature(srv):
    out = srv.convert_units(100, "C", "F")
    assert round(out["result"], 2) == 212.0


def test_convert_mismatched(srv):
    assert "error" in srv.convert_units(1, "kg", "m")
    assert "error" in srv.convert_units(1, "C", "kg")


# --- analyze_text / calculate / random_number ------------------------------

def test_analyze_text(srv):
    out = srv.analyze_text("Hello world. How are you?")
    assert out["words"] == 5
    assert out["sentences"] == 2


def test_calculate_ok(srv):
    assert srv.calculate("2 + 2 * 10") == "2 + 2 * 10 = 22"


def test_calculate_rejects_letters(srv):
    assert "Error" in srv.calculate("__import__('os')")


def test_random_number_in_range(srv):
    out = srv.random_number(1, 5)
    assert "Random number" in out


# --- notes tools (exercise the SQLite-backed CRUD via the server module) ---

def test_notes_crud_via_server(srv):
    created = srv.note_add("server-test", "body1")
    nid = created["id"]
    assert srv.note_get(nid)["title"] == "server-test"

    listed = srv.note_list(limit=10)
    assert listed["count"] >= 1
    assert any(n["id"] == nid for n in listed["notes"])

    updated = srv.note_update(nid, body="body2")
    assert updated["body"] == "body2"

    deleted = srv.note_delete(nid)
    assert deleted == {"deleted": True, "id": nid}
    assert "error" in srv.note_get(nid)


# --- resources ------------------------------------------------------------

def test_resource_server_info(srv):
    info = srv.resource_server_info()
    assert info["name"] == srv.SERVER_NAME
    assert info["version"] == srv.SERVER_VERSION
    assert "uptime_seconds" in info


# --- prompts --------------------------------------------------------------

def test_prompt_summarize(srv):
    out = srv.summarize_text("a long story", style="bullet points")
    assert "bullet points" in out
    assert "a long story" in out


def test_prompt_code_review(srv):
    out = srv.code_review("def f(): pass", language="python")
    assert "Bugs" in out and "python" in out


def test_prompt_explain_error(srv):
    out = srv.explain_error("ZeroDivisionError: division by zero", context="line 12 of foo.py")
    assert "ZeroDivisionError" in out
    assert "foo.py" in out
