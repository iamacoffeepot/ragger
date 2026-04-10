from __future__ import annotations

import math
import sqlite3
from collections import deque
from dataclasses import dataclass
from enum import Enum

from ragger.enums import ContentCategory, Facility, Region
from ragger.game_variable import GameVariable
from ragger.ground_item import GroundItem
from ragger.utils import snake_case
from ragger.shop import Shop


class DistanceMetric(str, Enum):
    CHEBYSHEV = "chebyshev"
    MANHATTAN = "manhattan"
    EUCLIDEAN = "euclidean"

    def compute(self, dx: int, dy: int) -> float:
        if self == DistanceMetric.CHEBYSHEV:
            return max(dx, dy)
        if self == DistanceMetric.MANHATTAN:
            return dx + dy
        if self == DistanceMetric.EUCLIDEAN:
            return math.sqrt(dx * dx + dy * dy)
        raise ValueError(f"Unhandled distance metric: {self}")


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
    facilities: int = 0

    def has_facility(self, facility: Facility) -> bool:
        return bool(self.facilities & facility.mask)

    def facility_list(self) -> list[Facility]:
        return [f for f in Facility if self.facilities & f.mask]

    @classmethod
    def all(
        cls,
        conn: sqlite3.Connection,
        region: Region | None = None,
    ) -> list[Location]:
        query = "SELECT id, name, region, type, members, x, y, facilities FROM locations"
        params: list = []

        if region is not None:
            query += " WHERE region = ?"
            params.append(region.value)

        query += " ORDER BY name"
        rows = conn.execute(query, params).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def with_facilities(
        cls,
        conn: sqlite3.Connection,
        facilities: list[Facility],
        region: Region | None = None,
    ) -> list[Location]:
        """Find all locations that have all of the specified facilities."""
        mask = 0
        for f in facilities:
            mask |= f.mask
        query = "SELECT id, name, region, type, members, x, y, facilities FROM locations WHERE facilities & ? = ?"
        params: list = [mask, mask]
        if region is not None:
            query += " AND region = ?"
            params.append(region.value)
        query += " ORDER BY name"
        rows = conn.execute(query, params).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def nearest(
        cls,
        conn: sqlite3.Connection,
        x: int,
        y: int,
        metric: DistanceMetric = DistanceMetric.CHEBYSHEV,
    ) -> Location | None:
        """Find the location with coordinates closest to the given point."""
        rows = conn.execute(
            "SELECT id, name, region, type, members, x, y, facilities FROM locations WHERE x IS NOT NULL AND y IS NOT NULL",
        ).fetchall()
        best: Location | None = None
        best_dist = float("inf")
        for row in rows:
            dx = abs(x - row[5])
            dy = abs(y - row[6])
            dist = metric.compute(dx, dy)
            if dist < best_dist:
                best_dist = dist
                best = cls._from_row(row)
        return best

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> Location | None:
        row = conn.execute(
            "SELECT id, name, region, type, members, x, y, facilities FROM locations WHERE name = ?",
            (name,),
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def search(cls, conn: sqlite3.Connection, name: str) -> list[Location]:
        rows = conn.execute(
            "SELECT id, name, region, type, members, x, y, facilities FROM locations WHERE name LIKE ? ORDER BY name",
            (f"%{name}%",),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

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
            facilities=row[7],
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

    def within(self, conn: sqlite3.Connection, hops: int) -> list[tuple[Location, int]]:
        """Return all locations reachable within `hops` via adjacency graph.

        Returns a list of (Location, hops) tuples sorted by hops then name.
        """
        visited: dict[int, tuple[Location, int]] = {self.id: (self, 0)}
        queue: deque[tuple[Location, int]] = deque([(self, 0)])

        while queue:
            current, depth = queue.popleft()
            if depth >= hops:
                continue
            for neighbor in current.neighbors(conn).values():
                if neighbor is not None and neighbor.id not in visited:
                    visited[neighbor.id] = (neighbor, depth + 1)
                    queue.append((neighbor, depth + 1))

        return sorted(visited.values(), key=lambda x: (x[1], x[0].name))

    def nearby(
        self,
        conn: sqlite3.Connection,
        max_distance: int,
        metric: DistanceMetric = DistanceMetric.CHEBYSHEV,
    ) -> list[tuple[Location, float]]:
        """Return locations within max_distance tiles, sorted by distance.

        Only includes locations with coordinates. Defaults to Chebyshev distance
        which matches OSRS diagonal movement (1 diagonal step = 1 tick).
        """
        if self.x is None or self.y is None:
            return []

        rows = conn.execute(
            """SELECT id, name, region, type, members, x, y, facilities FROM locations
               WHERE x IS NOT NULL AND y IS NOT NULL AND id != ?""",
            (self.id,),
        ).fetchall()

        results: list[tuple[Location, float]] = []
        for row in rows:
            loc = Location._from_row(row)
            dx = abs(self.x - loc.x)
            dy = abs(self.y - loc.y)
            dist = metric.compute(dx, dy)

            if dist <= max_distance:
                results.append((loc, dist))

        return sorted(results, key=lambda r: (r[1], r[0].name))

    def shops(self, conn: sqlite3.Connection) -> list[Shop]:
        """Return all shops at this location."""
        return Shop.all_at(conn, self.id)

    def ground_items(self, conn: sqlite3.Connection) -> list[GroundItem]:
        """Return all ground item spawns at this location."""
        return GroundItem.at_location(conn, self.id)

    @classmethod
    def for_shop(cls, conn: sqlite3.Connection, shop_id: int) -> Location | None:
        """Find the location for a given shop."""
        row = conn.execute(
            """SELECT l.id, l.name, l.region, l.type, l.members, l.x, l.y, l.facilities
               FROM locations l
               JOIN shops s ON s.location_id = l.id
               WHERE s.id = ?""",
            (shop_id,),
        ).fetchone()
        return cls._from_row(row) if row else None

    def game_vars(self, conn: sqlite3.Connection) -> list[GameVariable]:
        return GameVariable.by_content_tag(conn, ContentCategory.LOCATION, snake_case(self.name))
