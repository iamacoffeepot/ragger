from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from clogger.enums import MapLinkType

GAME_TILES_PER_REGION = 64
PIXELS_PER_REGION = 256


@dataclass
class MapSquare:
    id: int
    plane: int
    region_x: int
    region_y: int
    image: bytes

    @property
    def game_x(self) -> int:
        return self.region_x * GAME_TILES_PER_REGION

    @property
    def game_y(self) -> int:
        return self.region_y * GAME_TILES_PER_REGION

    @classmethod
    def get(cls, conn: sqlite3.Connection, plane: int, region_x: int, region_y: int) -> MapSquare | None:
        row = conn.execute(
            "SELECT id, plane, region_x, region_y, image FROM map_squares WHERE plane = ? AND region_x = ? AND region_y = ?",
            (plane, region_x, region_y),
        ).fetchone()
        return cls(*row) if row else None

    @classmethod
    def all(cls, conn: sqlite3.Connection, plane: int = 0) -> list[MapSquare]:
        rows = conn.execute(
            "SELECT id, plane, region_x, region_y, image FROM map_squares WHERE plane = ? ORDER BY region_x, region_y",
            (plane,),
        ).fetchall()
        return [cls(*row) for row in rows]

    @classmethod
    def at_game_coord(cls, conn: sqlite3.Connection, x: int, y: int, plane: int = 0) -> MapSquare | None:
        rx = x // GAME_TILES_PER_REGION
        ry = y // GAME_TILES_PER_REGION
        return cls.get(conn, plane, rx, ry)

    @classmethod
    def count(cls, conn: sqlite3.Connection, plane: int = 0) -> int:
        return conn.execute("SELECT COUNT(*) FROM map_squares WHERE plane = ?", (plane,)).fetchone()[0]


@dataclass
class MapLink:
    id: int
    src_location: str
    dst_location: str
    src_x: int
    src_y: int
    dst_x: int
    dst_y: int
    link_type: MapLinkType
    description: str | None

    @classmethod
    def all(cls, conn: sqlite3.Connection, link_type: MapLinkType | None = None) -> list[MapLink]:
        query = "SELECT id, src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description FROM map_links"
        params: list = []
        if link_type is not None:
            query += " WHERE type = ?"
            params.append(link_type.value)
        query += " ORDER BY src_location, dst_location"
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    def departing(cls, conn: sqlite3.Connection, location: str, link_type: MapLinkType | None = None) -> list[MapLink]:
        query = "SELECT id, src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description FROM map_links WHERE src_location = ?"
        params: list = [location]
        if link_type is not None:
            query += " AND type = ?"
            params.append(link_type.value)
        query += " ORDER BY type, dst_location"
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    def arriving(cls, conn: sqlite3.Connection, location: str, link_type: MapLinkType | None = None) -> list[MapLink]:
        query = "SELECT id, src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description FROM map_links WHERE dst_location = ?"
        params: list = [location]
        if link_type is not None:
            query += " AND type = ?"
            params.append(link_type.value)
        query += " ORDER BY type, src_location"
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    def between(cls, conn: sqlite3.Connection, location_a: str, location_b: str, link_type: MapLinkType | None = None) -> list[MapLink]:
        if link_type is not None:
            query = """SELECT id, src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description FROM map_links
                        WHERE ((src_location = ? AND dst_location = ?)
                            OR (src_location = ? AND dst_location = ?))
                          AND type = ?
                        ORDER BY type"""
            params = [location_a, location_b, location_b, location_a, link_type.value]
        else:
            query = """SELECT id, src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description FROM map_links
                        WHERE (src_location = ? AND dst_location = ?)
                           OR (src_location = ? AND dst_location = ?)
                        ORDER BY type"""
            params = [location_a, location_b, location_b, location_a]
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    def reachable_from(cls, conn: sqlite3.Connection, location: str) -> dict[str, list[MapLink]]:
        links = cls.departing(conn, location)
        result = {}
        for link in links:
            result.setdefault(link.dst_location, []).append(link)
        return result

    @classmethod
    def _from_row(cls, row: tuple):
        return cls(
            id=row[0],
            src_location=row[1],
            dst_location=row[2],
            src_x=row[3],
            src_y=row[4],
            dst_x=row[5],
            dst_y=row[6],
            link_type=MapLinkType(row[7]),
            description=row[8],
        )
