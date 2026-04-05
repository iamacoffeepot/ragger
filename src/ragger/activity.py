from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ragger.enums import ActivityType, Region, Skill


@dataclass
class Activity:
    id: int
    name: str
    type: ActivityType
    members: bool
    location: str | None
    location_id: int | None
    x: int | None
    y: int | None
    players: str | None
    skills: int
    region: Region | None

    _COLS = "id, name, type, members, location, location_id, x, y, players, skills, region"

    @classmethod
    def all(
        cls, conn: sqlite3.Connection, region: Region | None = None, activity_type: ActivityType | None = None
    ) -> list[Activity]:
        query = f"SELECT {cls._COLS} FROM activities"
        params: list = []
        clauses = []
        if region is not None:
            clauses.append("region = ?")
            params.append(region.value)
        if activity_type is not None:
            clauses.append("type = ?")
            params.append(activity_type.value)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY name"
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> Activity | None:
        row = conn.execute(
            f"SELECT {cls._COLS} FROM activities WHERE name = ?", (name,)
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def search(cls, conn: sqlite3.Connection, name: str) -> list[Activity]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM activities WHERE name LIKE ? ORDER BY name",
            (f"%{name}%",),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def by_type(cls, conn: sqlite3.Connection, activity_type: ActivityType) -> list[Activity]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM activities WHERE type = ? ORDER BY name",
            (activity_type.value,),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def for_skill(cls, conn: sqlite3.Connection, skill: Skill) -> list[Activity]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM activities WHERE (skills & ?) != 0 ORDER BY name",
            (skill.mask,),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def _from_row(cls, row: tuple) -> Activity:
        return cls(
            id=row[0],
            name=row[1],
            type=ActivityType(row[2]),
            members=bool(row[3]),
            location=row[4],
            location_id=row[5],
            x=row[6],
            y=row[7],
            players=row[8],
            skills=row[9],
            region=Region(row[10]) if row[10] is not None else None,
        )

    def skill_list(self) -> list[Skill]:
        return [s for s in Skill if self.skills & s.mask]
