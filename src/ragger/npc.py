from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ragger.dialogue import DialoguePage
from ragger.enums import ContentCategory, Region
from ragger.game_variable import GameVariable
from ragger.utils import snake_case


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
    def by_name(cls, conn: sqlite3.Connection, name: str, version: str | None = None) -> Npc | None:
        if version is not None:
            row = conn.execute(
                "SELECT id, name, version, location, x, y, options, region FROM npcs WHERE name = ? AND version = ?",
                (name, version),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id, name, version, location, x, y, options, region FROM npcs WHERE name = ? ORDER BY version LIMIT 1",
                (name,),
            ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def all_by_name(cls, conn: sqlite3.Connection, name: str) -> list[Npc]:
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

    def locations(self, conn: sqlite3.Connection) -> list[NpcLocation]:
        return NpcLocation.by_name(conn, self.name)

    def dialogues(self, conn: sqlite3.Connection) -> list[DialoguePage]:
        rows = conn.execute(
            """SELECT dp.id, dp.title, dp.page_type
               FROM dialogue_pages dp
               JOIN npc_dialogues nd ON nd.page_id = dp.id
               WHERE nd.npc_id = ?
               ORDER BY dp.title""",
            (self.id,),
        ).fetchall()
        return [DialoguePage(*r) for r in rows]

    def game_vars(self, conn: sqlite3.Connection) -> list[GameVariable]:
        return GameVariable.by_content_tag(conn, ContentCategory.NPC, snake_case(self.name))


@dataclass
class NpcLocation:
    id: int
    game_id: int
    name: str
    x: int
    y: int

    @classmethod
    def by_game_id(cls, conn: sqlite3.Connection, game_id: int) -> list[NpcLocation]:
        rows = conn.execute(
            "SELECT id, game_id, name, x, y FROM npc_locations WHERE game_id = ? ORDER BY x, y",
            (game_id,),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> list[NpcLocation]:
        rows = conn.execute(
            "SELECT id, game_id, name, x, y FROM npc_locations WHERE name = ? ORDER BY game_id, x, y",
            (name,),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def near(cls, conn: sqlite3.Connection, x: int, y: int, radius: int = 50) -> list[NpcLocation]:
        rows = conn.execute(
            """SELECT id, game_id, name, x, y FROM npc_locations
               WHERE ABS(x - ?) <= ? AND ABS(y - ?) <= ?
               ORDER BY ABS(x - ?) + ABS(y - ?)""",
            (x, radius, y, radius, x, y),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def _from_row(cls, row: tuple) -> NpcLocation:
        return cls(id=row[0], game_id=row[1], name=row[2], x=row[3], y=row[4])
