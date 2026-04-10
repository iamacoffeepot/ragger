"""Object (scenery) spawn location lookups."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class ObjectLocation:
    id: int
    game_id: int
    x: int
    y: int
    plane: int
    type: int
    orientation: int

    @classmethod
    def by_game_id(cls, conn: sqlite3.Connection, game_id: int) -> list[ObjectLocation]:
        rows = conn.execute(
            "SELECT id, game_id, x, y, plane, type, orientation FROM object_locations WHERE game_id = ? ORDER BY plane, x, y",
            (game_id,),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def near(cls, conn: sqlite3.Connection, x: int, y: int, radius: int = 50, plane: int = 0) -> list[ObjectLocation]:
        rows = conn.execute(
            """SELECT id, game_id, x, y, plane, type, orientation FROM object_locations
               WHERE plane = ? AND ABS(x - ?) <= ? AND ABS(y - ?) <= ?
               ORDER BY ABS(x - ?) + ABS(y - ?)""",
            (plane, x, radius, y, radius, x, y),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def _from_row(cls, row: tuple) -> ObjectLocation:
        return cls(id=row[0], game_id=row[1], x=row[2], y=row[3], plane=row[4], type=row[5], orientation=row[6])
