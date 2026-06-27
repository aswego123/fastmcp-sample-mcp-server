"""Unit tests for the SQLite-backed NotesDB.

Run with:
    pytest -q
"""

from __future__ import annotations

import pytest

from server.notes_db import NotesDB


@pytest.fixture()
def db(tmp_path):
    return NotesDB(tmp_path / "notes.db")


def test_add_and_get(db):
    note = db.add("first", "hello world")
    assert note["id"] >= 1
    assert note["title"] == "first"
    assert note["body"] == "hello world"
    assert note["created_at"] == note["updated_at"]

    fetched = db.get(note["id"])
    assert fetched == note


def test_add_strips_title_and_rejects_empty(db):
    note = db.add("  spaced  ")
    assert note["title"] == "spaced"

    with pytest.raises(ValueError):
        db.add("")
    with pytest.raises(ValueError):
        db.add("   ")


def test_list_newest_first_and_count(db):
    a = db.add("a")
    b = db.add("b")
    c = db.add("c")
    items = db.list()
    assert [n["id"] for n in items] == [c["id"], b["id"], a["id"]]
    assert db.count() == 3


def test_list_search(db):
    db.add("groceries", "milk, eggs")
    db.add("todo", "deploy server")
    db.add("ideas", "buy milk frother")
    results = db.list(search="milk")
    titles = {n["title"] for n in results}
    assert titles == {"groceries", "ideas"}


def test_list_limit_bounds(db):
    for i in range(5):
        db.add(f"n{i}")
    assert len(db.list(limit=2)) == 2
    # Limit is clamped to >= 1
    assert len(db.list(limit=0)) == 1


def test_update_partial(db):
    note = db.add("title1", "body1")
    updated = db.update(note["id"], body="body2")
    assert updated["title"] == "title1"
    assert updated["body"] == "body2"
    assert updated["updated_at"] >= note["updated_at"]

    updated2 = db.update(note["id"], title="title2")
    assert updated2["title"] == "title2"
    assert updated2["body"] == "body2"


def test_update_validation(db):
    note = db.add("x")
    with pytest.raises(ValueError):
        db.update(note["id"])  # no fields
    with pytest.raises(ValueError):
        db.update(note["id"], title="   ")
    assert db.update(99999, title="nope") is None


def test_delete(db):
    note = db.add("doomed")
    assert db.delete(note["id"]) is True
    assert db.get(note["id"]) is None
    assert db.delete(note["id"]) is False


def test_persistence(tmp_path):
    path = tmp_path / "persist.db"
    db1 = NotesDB(path)
    db1.add("survives")
    del db1

    db2 = NotesDB(path)
    items = db2.list()
    assert len(items) == 1
    assert items[0]["title"] == "survives"
