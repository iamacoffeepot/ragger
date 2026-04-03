from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from clogger.enums import Region


@dataclass
class Npc:
    id: int
    name: str
    version: str | None
    location: str | None
    x: int | None
    y: int | None
    options: str | None
    region: Region | None

    @classmethod
    def all(cls, conn: sqlite3.Connection, region: Region | None = None) -> list[Npc]:
        query = "SELECT id, name, version, location, x, y, options, region FROM npcs"
        params: list = []
        if region is not None:
            query += " WHERE region = ?"
            params.append(region.value)
        query += " ORDER BY name, version"
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> list[Npc]:
        rows = conn.execute(
            "SELECT id, name, version, location, x, y, options, region FROM npcs WHERE name = ? ORDER BY version",
            (name,),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def search(cls, conn: sqlite3.Connection, name: str) -> list[Npc]:
        rows = conn.execute(
            "SELECT id, name, version, location, x, y, options, region FROM npcs WHERE name LIKE ? ORDER BY name, version",
            (f"%{name}%",),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def with_option(cls, conn: sqlite3.Connection, option: str, region: Region | None = None) -> list[Npc]:
        query = "SELECT id, name, version, location, x, y, options, region FROM npcs WHERE options LIKE ?"
        params: list = [f"%{option}%"]
        if region is not None:
            query += " AND region = ?"
            params.append(region.value)
        query += " ORDER BY name, version"
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    def at_location(cls, conn: sqlite3.Connection, location: str) -> list[Npc]:
        rows = conn.execute(
            "SELECT id, name, version, location, x, y, options, region FROM npcs WHERE location LIKE ? ORDER BY name, version",
            (f"%{location}%",),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def _from_row(cls, row: tuple) -> Npc:
        return cls(
            id=row[0],
            name=row[1],
            version=row[2],
            location=row[3],
            x=row[4],
            y=row[5],
            options=row[6],
            region=Region(row[7]) if row[7] is not None else None,
        )

    def has_option(self, option: str) -> bool:
        if self.options is None:
            return False
        return option.lower() in self.options.lower()

    def option_list(self) -> list[str]:
        if self.options is None:
            return []
        return [o.strip() for o in self.options.split(",")]
