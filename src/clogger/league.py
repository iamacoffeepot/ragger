from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from clogger.enums import Region, TaskDifficulty
from clogger.requirements.diary import DiaryRequirement
from clogger.requirements.item import ItemRequirement
from clogger.requirements.quest import QuestRequirement
from clogger.requirements.skill import SkillRequirement


@dataclass
class LeagueTask:
    id: int
    name: str
    description: str
    difficulty: TaskDifficulty
    region: Region | None

    @property
    def points(self) -> int:
        return self.difficulty.points

    @classmethod
    def all(
        cls,
        conn: sqlite3.Connection,
        difficulty: TaskDifficulty | None = None,
        region: Region | None = None,
    ) -> list[LeagueTask]:
        query = "SELECT id, name, description, difficulty, region FROM league_tasks"
        params: list[int] = []
        conditions: list[str] = []

        if difficulty is not None:
            conditions.append("difficulty = ?")
            params.append(difficulty.value)
        if region is not None:
            conditions.append("region = ?")
            params.append(region.value)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id"

        rows = conn.execute(query, params).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> LeagueTask | None:
        row = conn.execute(
            "SELECT id, name, description, difficulty, region FROM league_tasks WHERE name = ?",
            (name,),
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def _from_row(cls, row: tuple) -> LeagueTask:
        return cls(
            id=row[0],
            name=row[1],
            description=row[2],
            difficulty=TaskDifficulty(row[3]),
            region=Region(row[4]) if row[4] is not None else None,
        )

    def skill_requirements(self, conn: sqlite3.Connection) -> list[SkillRequirement]:
        rows = conn.execute(
            """
            SELECT sr.id, sr.skill, sr.level
            FROM skill_requirements sr
            JOIN league_task_skill_requirements ltsr ON ltsr.skill_requirement_id = sr.id
            WHERE ltsr.league_task_id = ?
            ORDER BY sr.level DESC
            """,
            (self.id,),
        ).fetchall()
        return [SkillRequirement(row[0], row[1], row[2]) for row in rows]

    def quest_requirements(self, conn: sqlite3.Connection) -> list[QuestRequirement]:
        rows = conn.execute(
            """
            SELECT qr.id, qr.required_quest_id, qr.partial
            FROM quest_requirements qr
            JOIN league_task_quest_requirements ltqr ON ltqr.quest_requirement_id = qr.id
            WHERE ltqr.league_task_id = ?
            """,
            (self.id,),
        ).fetchall()
        return [QuestRequirement(row[0], row[1], bool(row[2])) for row in rows]

    def item_requirements(self, conn: sqlite3.Connection) -> list[ItemRequirement]:
        rows = conn.execute(
            """
            SELECT ir.id, ir.item_id, ir.quantity
            FROM item_requirements ir
            JOIN league_task_item_requirements ltir ON ltir.item_requirement_id = ir.id
            WHERE ltir.league_task_id = ?
            """,
            (self.id,),
        ).fetchall()
        return [ItemRequirement(*row) for row in rows]

    def diary_requirements(self, conn: sqlite3.Connection) -> list[DiaryRequirement]:
        rows = conn.execute(
            """
            SELECT dr.id, dr.location, dr.tier
            FROM diary_requirements dr
            JOIN league_task_diary_requirements ltdr ON ltdr.diary_requirement_id = dr.id
            WHERE ltdr.league_task_id = ?
            """,
            (self.id,),
        ).fetchall()
        return [DiaryRequirement(row[0], row[1], row[2]) for row in rows]
