from __future__ import annotations

import sqlite3
from collections import deque
from dataclasses import dataclass

from clogger.enums import Region
from clogger.shop import Shop


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
    x: int | None = None
    y: int | None = None

    @classmethod
    def all(
        cls,
        conn: sqlite3.Connection,
        region: Region | None = None,
    ) -> list[Location]:
        query = "SELECT id, name, region, type, members, x, y FROM locations"
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
            "SELECT id, name, region, type, members, x, y FROM locations WHERE name = ?",
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
            x=row[5],
            y=row[6],
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

    def within(self, conn: sqlite3.Connection, distance: int) -> list[tuple[Location, int]]:
        """Return all locations reachable within `distance` hops via adjacency graph.

        Returns a list of (Location, distance) tuples sorted by distance then name.
        """
        visited: dict[int, tuple[Location, int]] = {self.id: (self, 0)}
        queue: deque[tuple[Location, int]] = deque([(self, 0)])

        while queue:
            current, depth = queue.popleft()
            if depth >= distance:
                continue
            for neighbor in current.neighbors(conn).values():
                if neighbor is not None and neighbor.id not in visited:
                    visited[neighbor.id] = (neighbor, depth + 1)
                    queue.append((neighbor, depth + 1))

        return sorted(visited.values(), key=lambda x: (x[1], x[0].name))

    def shops(self, conn: sqlite3.Connection) -> list[Shop]:
        """Return all shops at this location."""
        return Shop.all_at(conn, self.id)

    @classmethod
    def for_shop(cls, conn: sqlite3.Connection, shop_id: int) -> Location | None:
        """Find the location for a given shop."""
        row = conn.execute(
            """SELECT l.id, l.name, l.region, l.type, l.members, l.x, l.y
               FROM locations l
               JOIN shops s ON s.location_id = l.id
               WHERE s.id = ?""",
            (shop_id,),
        ).fetchone()
        return cls._from_row(row) if row else None
