from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from clogger.enums import Region


@dataclass
class Adjacency:
    id: int
    location_id: int
    direction: str
    neighbor: str


@dataclass
class Location:
    id: int
    name: str
    region: Region | None
    type: str | None
    members: bool

    @classmethod
    def all(
        cls,
        conn: sqlite3.Connection,
        region: Region | None = None,
    ) -> list[Location]:
        query = "SELECT id, name, region, type, members FROM locations"
        params: list = []

        if region is not None:
            query += " WHERE region = ?"
            params.append(region.value)

        query += " ORDER BY name"
        rows = conn.execute(query, params).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> Location | None:
        row = conn.execute(
            "SELECT id, name, region, type, members FROM locations WHERE name = ?",
            (name,),
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def _from_row(cls, row: tuple) -> Location:
        return cls(
            id=row[0],
            name=row[1],
            region=Region(row[2]) if row[2] is not None else None,
            type=row[3],
            members=bool(row[4]),
        )

    def adjacencies(self, conn: sqlite3.Connection) -> list[Adjacency]:
        rows = conn.execute(
            "SELECT id, location_id, direction, neighbor FROM location_adjacencies WHERE location_id = ? ORDER BY direction",
            (self.id,),
        ).fetchall()
        return [Adjacency(*row) for row in rows]

    def neighbors(self, conn: sqlite3.Connection) -> dict[str, Location | None]:
        """Return adjacent locations as a dict keyed by direction.

        Values are Location objects if the neighbor exists in the database, None otherwise.
        """
        adjs = self.adjacencies(conn)
        result: dict[str, Location | None] = {}
        for adj in adjs:
            result[adj.direction] = Location.by_name(conn, adj.neighbor)
        return result
