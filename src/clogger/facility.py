from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from clogger.enums import Facility as FacilityType, Region
from clogger.location import DistanceMetric


@dataclass
class FacilityEntry:
    id: int
    type: FacilityType
    x: int
    y: int
    name: str | None
    region: Region | None = None

    @classmethod
    def all(
        cls,
        conn: sqlite3.Connection,
        facility_type: FacilityType | None = None,
        region: Region | None = None,
    ) -> list[FacilityEntry]:
        query = "SELECT id, type, x, y, name, region FROM facilities"
        params: list = []
        conditions: list[str] = []
        if facility_type is not None:
            conditions.append("type = ?")
            params.append(facility_type.value)
        if region is not None:
            conditions.append("region = ?")
            params.append(region.value)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id"
        rows = conn.execute(query, params).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def nearest(
        cls,
        conn: sqlite3.Connection,
        x: int,
        y: int,
        facility_type: FacilityType | None = None,
        metric: DistanceMetric = DistanceMetric.CHEBYSHEV,
    ) -> FacilityEntry | None:
        """Find the nearest facility to the given coordinates."""
        query = "SELECT id, type, x, y, name, region FROM facilities"
        params: list = []
        if facility_type is not None:
            query += " WHERE type = ?"
            params.append(facility_type.value)
        rows = conn.execute(query, params).fetchall()

        best: FacilityEntry | None = None
        best_dist = float("inf")
        for row in rows:
            dx = abs(x - row[2])
            dy = abs(y - row[3])
            dist = metric.compute(dx, dy)
            if dist < best_dist:
                best_dist = dist
                best = cls._from_row(row)
        return best

    @classmethod
    def nearby(
        cls,
        conn: sqlite3.Connection,
        x: int,
        y: int,
        max_distance: int,
        facility_type: FacilityType | None = None,
        metric: DistanceMetric = DistanceMetric.CHEBYSHEV,
    ) -> list[tuple[FacilityEntry, float]]:
        """Find all facilities within max_distance of the given coordinates."""
        query = "SELECT id, type, x, y, name, region FROM facilities"
        params: list = []
        if facility_type is not None:
            query += " WHERE type = ?"
            params.append(facility_type.value)
        rows = conn.execute(query, params).fetchall()

        results: list[tuple[FacilityEntry, float]] = []
        for row in rows:
            dx = abs(x - row[2])
            dy = abs(y - row[3])
            dist = metric.compute(dx, dy)
            if dist <= max_distance:
                results.append((cls._from_row(row), dist))

        return sorted(results, key=lambda r: (r[1], r[0].name or ""))

    @classmethod
    def _from_row(cls, row: tuple) -> FacilityEntry:
        return cls(
            id=row[0],
            type=FacilityType(row[1]),
            x=row[2],
            y=row[3],
            name=row[4],
            region=Region(row[5]) if row[5] is not None else None,
        )
