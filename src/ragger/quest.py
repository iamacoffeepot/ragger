from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ragger.dialogue import DialoguePage
from ragger.enums import ComparisonOperator, ContentCategory, Region, Skill
from ragger.game_variable import GameVariable
from ragger.requirements import (
    GroupQuestPointRequirement,
    GroupQuestRequirement,
    GroupRegionRequirement,
    GroupSkillRequirement,
    RequirementGroup,
)
from ragger.rewards import ExperienceReward, ItemReward
from ragger.utils import snake_case


@dataclass
class Quest:
    id: int
    name: str
    points: int

    @classmethod
    def all(cls, conn: sqlite3.Connection) -> list[Quest]:
        rows = conn.execute("SELECT id, name, points FROM quests ORDER BY name").fetchall()
        return [cls(*row) for row in rows]

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> Quest | None:
        row = conn.execute("SELECT id, name, points FROM quests WHERE name = ?", (name,)).fetchone()
        return cls(*row) if row else None

    @classmethod
    def search(cls, conn: sqlite3.Connection, name: str) -> list[Quest]:
        rows = conn.execute(
            "SELECT id, name, points FROM quests WHERE name LIKE ? ORDER BY name",
            (f"%{name}%",),
        ).fetchall()
        return [cls(*row) for row in rows]

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

    def requirement_groups(self, conn: sqlite3.Connection) -> list[RequirementGroup]:
        return RequirementGroup.for_quest(conn, self.id)

    def skill_requirements(self, conn: sqlite3.Connection) -> list[GroupSkillRequirement]:
        rows = conn.execute(
            """
            SELECT gsr.id, gsr.group_id, gsr.skill, gsr.level, gsr.boostable, gsr.operator
            FROM group_skill_requirements gsr
            JOIN quest_requirement_groups qrg ON qrg.group_id = gsr.group_id
            WHERE qrg.quest_id = ?
            ORDER BY gsr.level DESC
            """,
            (self.id,),
        ).fetchall()
        return [GroupSkillRequirement(r[0], r[1], Skill(r[2]), r[3], bool(r[4]), ComparisonOperator(r[5])) for r in rows]

    def quest_requirements(self, conn: sqlite3.Connection) -> list[GroupQuestRequirement]:
        rows = conn.execute(
            """
            SELECT gqr.id, gqr.group_id, gqr.required_quest_id, gqr.partial
            FROM group_quest_requirements gqr
            JOIN quest_requirement_groups qrg ON qrg.group_id = gqr.group_id
            WHERE qrg.quest_id = ?
            """,
            (self.id,),
        ).fetchall()
        return [GroupQuestRequirement(r[0], r[1], r[2], bool(r[3])) for r in rows]

    def quest_point_requirement(self, conn: sqlite3.Connection) -> GroupQuestPointRequirement | None:
        row = conn.execute(
            """
            SELECT gqpr.id, gqpr.group_id, gqpr.points, gqpr.operator
            FROM group_quest_point_requirements gqpr
            JOIN quest_requirement_groups qrg ON qrg.group_id = gqpr.group_id
            WHERE qrg.quest_id = ?
            """,
            (self.id,),
        ).fetchone()
        return GroupQuestPointRequirement(row[0], row[1], row[2], ComparisonOperator(row[3])) if row else None

    def region_requirements(self, conn: sqlite3.Connection) -> list[GroupRegionRequirement]:
        rows = conn.execute(
            """
            SELECT grr.id, grr.group_id, grr.region
            FROM group_region_requirements grr
            JOIN quest_requirement_groups qrg ON qrg.group_id = grr.group_id
            WHERE qrg.quest_id = ?
            """,
            (self.id,),
        ).fetchall()
        return [GroupRegionRequirement(r[0], r[1], Region(r[2])) for r in rows]

    def requirement_chain(self, conn: sqlite3.Connection) -> list[Quest]:
        """Recursively resolve all quests required to complete this quest."""
        visited: set[int] = set()
        chain: list[Quest] = []

        def _traverse(quest_id: int) -> None:
            rows = conn.execute(
                """
                SELECT q.id, q.name, q.points
                FROM quests q
                JOIN group_quest_requirements gqr ON gqr.required_quest_id = q.id
                JOIN quest_requirement_groups qrg ON qrg.group_id = gqr.group_id
                WHERE qrg.quest_id = ?
                """,
                (quest_id,),
            ).fetchall()
            for row in rows:
                if row[0] not in visited:
                    visited.add(row[0])
                    _traverse(row[0])
                    chain.append(Quest(*row))

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
                JOIN group_quest_requirements gqr ON gqr.required_quest_id = q.id
                JOIN quest_requirement_groups qrg ON qrg.group_id = gqr.group_id
                WHERE qrg.quest_id = ?
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

    def dialogues(self, conn: sqlite3.Connection) -> list[DialoguePage]:
        rows = conn.execute(
            """SELECT dp.id, dp.title, dp.page_type
               FROM dialogue_pages dp
               JOIN quest_dialogues qd ON qd.page_id = dp.id
               WHERE qd.quest_id = ?
               ORDER BY dp.title""",
            (self.id,),
        ).fetchall()
        return [DialoguePage(*r) for r in rows]

    def game_vars(self, conn: sqlite3.Connection) -> list[GameVariable]:
        return GameVariable.by_content_tag(conn, ContentCategory.QUEST, snake_case(self.name))
