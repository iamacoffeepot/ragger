import sqlite3

from ragger.item import Item


def _seed_items(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO items (name) VALUES (?)",
        [("Coins",), ("Rope",), ("Spade",)],
    )
    conn.commit()


def test_all(conn: sqlite3.Connection) -> None:
    _seed_items(conn)
    items = Item.all(conn)
    assert len(items) == 3
    assert all(isinstance(i, Item) for i in items)
    assert items[0].name == "Coins"


def test_by_name(conn: sqlite3.Connection) -> None:
    _seed_items(conn)
    item = Item.by_name(conn, "Rope")
    assert item is not None
    assert item.name == "Rope"


def test_by_name_not_found(conn: sqlite3.Connection) -> None:
    _seed_items(conn)
    assert Item.by_name(conn, "Nonexistent") is None
