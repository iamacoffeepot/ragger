from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class Item:
    id: int
    name: str
    members: bool | None
    tradeable: bool | None
    weight: float | None
    examine: str | None
    value: int | None

    _COLS = "id, name, members, tradeable, weight, examine, value"

    @classmethod
    def all(cls, conn: sqlite3.Connection) -> list[Item]:
        rows = conn.execute(f"SELECT {cls._COLS} FROM items ORDER BY name").fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> Item | None:
        row = conn.execute(
            f"SELECT {cls._COLS} FROM items WHERE name = ?", (name,)
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def by_game_id(cls, conn: sqlite3.Connection, game_id: int) -> Item | None:
        row = conn.execute(
            f"""SELECT {cls._COLS} FROM items i
                JOIN item_game_ids g ON g.item_id = i.id
                WHERE g.game_id = ?""",
            (game_id,),
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def search(cls, conn: sqlite3.Connection, name: str) -> list[Item]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM items WHERE name LIKE ? ORDER BY name",
            (f"%{name}%",),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    def game_ids(self, conn: sqlite3.Connection) -> list[int]:
        rows = conn.execute(
            "SELECT game_id FROM item_game_ids WHERE item_id = ? ORDER BY game_id",
            (self.id,),
        ).fetchall()
        return [row[0] for row in rows]

    @classmethod
    def _from_row(cls, row: tuple) -> Item:
        return cls(
            id=row[0],
            name=row[1],
            members=bool(row[2]) if row[2] is not None else None,
            tradeable=bool(row[3]) if row[3] is not None else None,
            weight=row[4],
            examine=row[5],
            value=row[6],
        )
