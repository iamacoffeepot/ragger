from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ragger.enums import DiaryLocation, DiaryTier
from ragger.requirements import RequirementGroup


@dataclass
class DiaryTask:
    id: int
    location: DiaryLocation
    tier: DiaryTier
    description: str

    def requirement_groups(self, conn: sqlite3.Connection) -> list[RequirementGroup]:
        return RequirementGroup.for_diary_task(conn, self.id)

    @classmethod
    def all(
        cls,
        conn: sqlite3.Connection,
        location: DiaryLocation | None = None,
        tier: DiaryTier | None = None,
    ) -> list[DiaryTask]:
        query = "SELECT id, location, tier, description FROM diary_tasks"
        params: list = []
        conditions: list[str] = []

        if location is not None:
            conditions.append("location = ?")
            params.append(location.value)
        if tier is not None:
            conditions.append("tier = ?")
            params.append(tier.value)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY location, tier, id"

        rows = conn.execute(query, params).fetchall()
        return [cls(row[0], DiaryLocation(row[1]), DiaryTier(row[2]), row[3]) for row in rows]
