from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ragger.enums import Region


@dataclass
class GroundItem:
    id: int
    item_name: str
    item_id: int | None
    location: str
    location_id: int | None
    members: bool
    x: int
    y: int
    plane: int
    region: Region | None

    _COLS = "id, item_name, item_id, location, location_id, members, x, y, plane, region"

    @classmethod
    def all(cls, conn: sqlite3.Connection, region: Region | None = None) -> list[GroundItem]:
        query = f"SELECT {cls._COLS} FROM ground_items"
        params: list = []
        if region is not None:
            query += " WHERE region = ?"
            params.append(region.value)
        query += " ORDER BY item_name, x, y"
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    def by_item_name(cls, conn: sqlite3.Connection, name: str) -> list[GroundItem]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM ground_items WHERE item_name = ? ORDER BY location, x, y",
            (name,),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def by_item_id(cls, conn: sqlite3.Connection, item_id: int) -> list[GroundItem]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM ground_items WHERE item_id = ? ORDER BY location, x, y",
            (item_id,),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def search(cls, conn: sqlite3.Connection, name: str) -> list[GroundItem]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM ground_items WHERE item_name LIKE ? ORDER BY item_name, x, y",
            (f"%{name}%",),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def at_location(cls, conn: sqlite3.Connection, location_id: int) -> list[GroundItem]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM ground_items WHERE location_id = ? ORDER BY item_name, x, y",
            (location_id,),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def near(cls, conn: sqlite3.Connection, x: int, y: int, radius: int = 50) -> list[GroundItem]:
        rows = conn.execute(
            f"""SELECT {cls._COLS} FROM ground_items
                WHERE ABS(x - ?) <= ? AND ABS(y - ?) <= ?
                ORDER BY ABS(x - ?) + ABS(y - ?)""",
            (x, radius, y, radius, x, y),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def _from_row(cls, row: tuple) -> GroundItem:
        return cls(
            id=row[0],
            item_name=row[1],
            item_id=row[2],
            location=row[3],
            location_id=row[4],
            members=bool(row[5]),
            x=row[6],
            y=row[7],
            plane=row[8],
            region=Region(row[9]) if row[9] is not None else None,
        )
