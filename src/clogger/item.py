from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class Item:
    id: int
    name: str

    @classmethod
    def all(cls, conn: sqlite3.Connection) -> list[Item]:
        rows = conn.execute("SELECT id, name FROM items ORDER BY name").fetchall()
        return [cls(*row) for row in rows]

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> Item | None:
        row = conn.execute("SELECT id, name FROM items WHERE name = ?", (name,)).fetchone()
        return cls(*row) if row else None
