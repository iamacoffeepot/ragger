from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from clogger.requirements.quest import QuestRequirement
from clogger.requirements.quest_point import QuestPointRequirement
from clogger.requirements.skill import SkillRequirement
from clogger.rewards.experience import ExperienceReward
from clogger.rewards.item import ItemReward


@dataclass
class Quest:
    id: int
    name: str
    points: int
    autocompleted: bool

    @classmethod
    def all(cls, conn: sqlite3.Connection) -> list[Quest]:
        rows = conn.execute("SELECT id, name, points, autocompleted FROM quests ORDER BY name").fetchall()
        return [cls(row[0], row[1], row[2], bool(row[3])) for row in rows]

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> Quest | None:
        row = conn.execute("SELECT id, name, points, autocompleted FROM quests WHERE name = ?", (name,)).fetchone()
        return cls(row[0], row[1], row[2], bool(row[3])) if row else None

    def xp_rewards(self, conn: sqlite3.Connection) -> list[ExperienceReward]:
        rows = conn.execute(
            """
            SELECT er.id, er.eligible_skills, er.amount
            FROM experience_rewards er
            JOIN quest_experience_rewards qer ON qer.experience_reward_id = er.id
            WHERE qer.quest_id = ?
            ORDER BY er.amount DESC
            """,
            (self.id,),
        ).fetchall()
        return [ExperienceReward(*row) for row in rows]

    def item_rewards(self, conn: sqlite3.Connection) -> list[ItemReward]:
        rows = conn.execute(
            """
            SELECT ir.id, ir.item_id, ir.quantity
            FROM item_rewards ir
            JOIN quest_item_rewards qir ON qir.item_reward_id = ir.id
            WHERE qir.quest_id = ?
            ORDER BY ir.quantity DESC
            """,
            (self.id,),
        ).fetchall()
        return [ItemReward(*row) for row in rows]

    def skill_requirements(self, conn: sqlite3.Connection) -> list[SkillRequirement]:
        rows = conn.execute(
            """
            SELECT sr.id, sr.skill, sr.level
            FROM skill_requirements sr
            JOIN quest_skill_requirements qsr ON qsr.skill_requirement_id = sr.id
            WHERE qsr.quest_id = ?
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
            JOIN quest_quest_requirements qqr ON qqr.quest_requirement_id = qr.id
            WHERE qqr.quest_id = ?
            """,
            (self.id,),
        ).fetchall()
        return [QuestRequirement(row[0], row[1], bool(row[2])) for row in rows]

    def quest_point_requirement(self, conn: sqlite3.Connection) -> QuestPointRequirement | None:
        row = conn.execute(
            """
            SELECT qpr.id, qpr.points
            FROM quest_point_requirements qpr
            JOIN quest_quest_point_requirements qqpr ON qqpr.quest_point_requirement_id = qpr.id
            WHERE qqpr.quest_id = ?
            """,
            (self.id,),
        ).fetchone()
        return QuestPointRequirement(*row) if row else None

    def requirement_chain(self, conn: sqlite3.Connection) -> list[Quest]:
        """Recursively resolve all quests required to complete this quest."""
        visited: set[int] = set()
        chain: list[Quest] = []

        def _traverse(quest_id: int) -> None:
            rows = conn.execute(
                """
                SELECT q.id, q.name, q.points, q.autocompleted
                FROM quests q
                JOIN quest_requirements qr ON qr.required_quest_id = q.id
                JOIN quest_quest_requirements qqr ON qqr.quest_requirement_id = qr.id
                WHERE qqr.quest_id = ?
                """,
                (quest_id,),
            ).fetchall()
            for row in rows:
                if row[0] not in visited:
                    visited.add(row[0])
                    _traverse(row[0])
                    chain.append(Quest(row[0], row[1], row[2], bool(row[3])))

        _traverse(self.id)
        return chain

    def requirement_tree(self, conn: sqlite3.Connection) -> str:
        """Return a string representation of the quest requirement tree."""
        lines: list[str] = []
        visited: set[int] = set()

        def _build(quest_id: int, name: str, depth: int) -> None:
            rows = conn.execute(
                """
                SELECT q.id, q.name
                FROM quests q
                JOIN quest_requirements qr ON qr.required_quest_id = q.id
                JOIN quest_quest_requirements qqr ON qqr.quest_requirement_id = qr.id
                WHERE qqr.quest_id = ?
                ORDER BY q.name
                """,
                (quest_id,),
            ).fetchall()
            for req_id, req_name in rows:
                prefix = "  " * depth + "└─ "
                if req_id in visited:
                    lines.append(f"{prefix}{req_name} (see above)")
                else:
                    visited.add(req_id)
                    lines.append(f"{prefix}{req_name}")
                    _build(req_id, req_name, depth + 1)

        lines.append(self.name)
        visited.add(self.id)
        _build(self.id, self.name, 1)
        return "\n".join(lines)
