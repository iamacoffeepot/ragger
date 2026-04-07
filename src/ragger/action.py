from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ragger.enums import Skill, ActionTriggerType
from ragger.requirements import (
    GroupQuestRequirement,
    GroupSkillRequirement,
    RequirementGroup,
)


@dataclass
class ActionOutputExperience:
    skill: Skill
    xp: float


@dataclass
class ActionInputItem:
    item_id: int | None
    item_name: str
    quantity: int


@dataclass
class ActionInputObject:
    object_name: str


@dataclass
class ActionInputCurrency:
    currency: str
    quantity: int


@dataclass
class ActionOutputItem:
    item_id: int | None
    item_name: str
    quantity: int


@dataclass
class ActionOutputObject:
    object_name: str


@dataclass
class ActionTrigger:
    trigger_type: ActionTriggerType
    source_id: int | None
    target_id: int
    op: str


@dataclass
class Action:
    id: int
    name: str
    members: bool
    ticks: int | None
    notes: str | None

    _COLS = "id, name, members, ticks, notes"

    # --- Core queries ---

    @classmethod
    def all(cls, conn: sqlite3.Connection) -> list[Action]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM actions ORDER BY id",
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> list[Action]:
        """Find actions by exact name (may have multiple methods for same output)."""
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM actions WHERE name = ? ORDER BY id",
            (name,),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def search(cls, conn: sqlite3.Connection, name: str) -> list[Action]:
        """Find actions whose name matches a partial string."""
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM actions WHERE name LIKE ? ORDER BY name, id",
            (f"%{name}%",),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def by_trigger_type(cls, conn: sqlite3.Connection, trigger_type: ActionTriggerType) -> list[Action]:
        """Find actions that have triggers of a given type."""
        rows = conn.execute(
            f"""SELECT DISTINCT a.{cls._COLS.replace(', ', ', a.')}
                FROM actions a
                JOIN action_triggers at ON at.action_id = a.id
                WHERE at.trigger_type = ?
                ORDER BY a.id""",
            (trigger_type.value,),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def by_trigger(
        cls, conn: sqlite3.Connection, trigger_type: ActionTriggerType, target_id: int, op: str | None = None,
    ) -> list[Action]:
        """Find actions matching a game interaction event.

        Looks up actions whose action_triggers match the given trigger_type
        and target_id (and optionally op).
        """
        if op is not None:
            rows = conn.execute(
                f"""SELECT DISTINCT a.{cls._COLS.replace(', ', ', a.')}
                    FROM actions a
                    JOIN action_triggers at ON at.action_id = a.id
                    WHERE at.trigger_type = ? AND at.target_id = ? AND at.op = ?
                    ORDER BY a.id""",
                (trigger_type.value, target_id, op),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""SELECT DISTINCT a.{cls._COLS.replace(', ', ', a.')}
                    FROM actions a
                    JOIN action_triggers at ON at.action_id = a.id
                    WHERE at.trigger_type = ? AND at.target_id = ?
                    ORDER BY a.id""",
                (trigger_type.value, target_id),
            ).fetchall()
        return [cls._from_row(row) for row in rows]

    # --- Producing queries ---

    @classmethod
    def producing_item(cls, conn: sqlite3.Connection, item_name: str) -> list[Action]:
        """Find actions that produce a given item."""
        rows = conn.execute(
            f"""SELECT a.{cls._COLS.replace(', ', ', a.')}
                FROM actions a
                JOIN action_output_items ao ON ao.action_id = a.id
                WHERE ao.item_name = ?
                ORDER BY a.id""",
            (item_name,),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def producing_object(cls, conn: sqlite3.Connection, object_name: str) -> list[Action]:
        """Find actions that produce a given object."""
        rows = conn.execute(
            f"""SELECT a.{cls._COLS.replace(', ', ', a.')}
                FROM actions a
                JOIN action_output_objects ao ON ao.action_id = a.id
                WHERE ao.object_name = ?
                ORDER BY a.id""",
            (object_name,),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def producing_experience(cls, conn: sqlite3.Connection, skill: Skill) -> list[Action]:
        """Find actions that grant experience in a given skill."""
        rows = conn.execute(
            f"""SELECT DISTINCT a.{cls._COLS.replace(', ', ', a.')}
                FROM actions a
                JOIN action_output_experience ae ON ae.action_id = a.id
                WHERE ae.skill = ?
                ORDER BY a.id""",
            (skill.value,),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    # --- Consuming queries ---

    @classmethod
    def consuming_item(cls, conn: sqlite3.Connection, item_name: str) -> list[Action]:
        """Find actions that consume a given item as input."""
        rows = conn.execute(
            f"""SELECT a.{cls._COLS.replace(', ', ', a.')}
                FROM actions a
                JOIN action_input_items ai ON ai.action_id = a.id
                WHERE ai.item_name = ?
                ORDER BY a.id""",
            (item_name,),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def consuming_object(cls, conn: sqlite3.Connection, object_name: str) -> list[Action]:
        """Find actions that consume a given object as input."""
        rows = conn.execute(
            f"""SELECT a.{cls._COLS.replace(', ', ', a.')}
                FROM actions a
                JOIN action_input_objects ao ON ao.action_id = a.id
                WHERE ao.object_name = ?
                ORDER BY a.id""",
            (object_name,),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def consuming_currency(cls, conn: sqlite3.Connection, currency: str) -> list[Action]:
        """Find actions that consume a given currency as input."""
        rows = conn.execute(
            f"""SELECT a.{cls._COLS.replace(', ', ', a.')}
                FROM actions a
                JOIN action_input_currencies ac ON ac.action_id = a.id
                WHERE ac.currency = ?
                ORDER BY a.id""",
            (currency,),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    # --- Output methods ---

    def output_experience(self, conn: sqlite3.Connection) -> list[ActionOutputExperience]:
        rows = conn.execute(
            "SELECT skill, xp FROM action_output_experience WHERE action_id = ? ORDER BY skill",
            (self.id,),
        ).fetchall()
        return [ActionOutputExperience(skill=Skill(row[0]), xp=row[1]) for row in rows]

    def output_items(self, conn: sqlite3.Connection) -> list[ActionOutputItem]:
        rows = conn.execute(
            "SELECT item_id, item_name, quantity FROM action_output_items WHERE action_id = ? ORDER BY item_name",
            (self.id,),
        ).fetchall()
        return [ActionOutputItem(item_id=row[0], item_name=row[1], quantity=row[2]) for row in rows]

    def output_objects(self, conn: sqlite3.Connection) -> list[ActionOutputObject]:
        rows = conn.execute(
            "SELECT object_name FROM action_output_objects WHERE action_id = ? ORDER BY object_name",
            (self.id,),
        ).fetchall()
        return [ActionOutputObject(object_name=row[0]) for row in rows]

    # --- Input methods ---

    def input_items(self, conn: sqlite3.Connection) -> list[ActionInputItem]:
        rows = conn.execute(
            "SELECT item_id, item_name, quantity FROM action_input_items WHERE action_id = ? ORDER BY item_name",
            (self.id,),
        ).fetchall()
        return [ActionInputItem(item_id=row[0], item_name=row[1], quantity=row[2]) for row in rows]

    def input_objects(self, conn: sqlite3.Connection) -> list[ActionInputObject]:
        rows = conn.execute(
            "SELECT object_name FROM action_input_objects WHERE action_id = ? ORDER BY object_name",
            (self.id,),
        ).fetchall()
        return [ActionInputObject(object_name=row[0]) for row in rows]

    def input_currencies(self, conn: sqlite3.Connection) -> list[ActionInputCurrency]:
        rows = conn.execute(
            "SELECT currency, quantity FROM action_input_currencies WHERE action_id = ? ORDER BY currency",
            (self.id,),
        ).fetchall()
        return [ActionInputCurrency(currency=row[0], quantity=row[1]) for row in rows]

    # --- Trigger methods ---

    def triggers(self, conn: sqlite3.Connection) -> list[ActionTrigger]:
        rows = conn.execute(
            "SELECT trigger_type, source_id, target_id, op FROM action_triggers WHERE action_id = ? ORDER BY trigger_type, target_id, op",
            (self.id,),
        ).fetchall()
        return [ActionTrigger(trigger_type=ActionTriggerType(row[0]), source_id=row[1], target_id=row[2], op=row[3]) for row in rows]

    # --- Requirement methods ---

    def requirement_groups(self, conn: sqlite3.Connection) -> list[RequirementGroup]:
        return RequirementGroup.for_action(conn, self.id)

    def skill_requirements(self, conn: sqlite3.Connection) -> list[GroupSkillRequirement]:
        rows = conn.execute(
            """
            SELECT gsr.id, gsr.group_id, gsr.skill, gsr.level, gsr.boostable
            FROM group_skill_requirements gsr
            JOIN action_requirement_groups arg ON arg.group_id = gsr.group_id
            WHERE arg.action_id = ?
            ORDER BY gsr.level DESC
            """,
            (self.id,),
        ).fetchall()
        return [GroupSkillRequirement(r[0], r[1], Skill(r[2]), r[3], bool(r[4])) for r in rows]

    def quest_requirements(self, conn: sqlite3.Connection) -> list[GroupQuestRequirement]:
        rows = conn.execute(
            """
            SELECT gqr.id, gqr.group_id, gqr.required_quest_id, gqr.partial
            FROM group_quest_requirements gqr
            JOIN action_requirement_groups arg ON arg.group_id = gqr.group_id
            WHERE arg.action_id = ?
            """,
            (self.id,),
        ).fetchall()
        return [GroupQuestRequirement(r[0], r[1], r[2], bool(r[3])) for r in rows]

    # --- Deletion ---

    @staticmethod
    def delete_by_source(conn: sqlite3.Connection, source: str) -> list[int]:
        """Delete all actions for a source and their dependent rows.

        Cleans up input/output tables, requirement group junctions, orphaned
        requirement groups and their child requirements, source_actions, and
        the actions themselves. Returns the deleted action IDs.
        """
        old_ids = [r[0] for r in conn.execute(
            "SELECT action_id FROM source_actions WHERE source = ?", (source,),
        ).fetchall()]
        if not old_ids:
            return []

        ph = ",".join("?" * len(old_ids))

        # Collect requirement group IDs before deleting junctions
        group_ids = [r[0] for r in conn.execute(
            f"SELECT group_id FROM action_requirement_groups WHERE action_id IN ({ph})",
            old_ids,
        ).fetchall()]

        # Delete action-dependent rows
        for table in (
            "action_triggers",
            "action_requirement_groups",
            "action_output_objects",
            "action_output_items",
            "action_output_experience",
            "action_input_currencies",
            "action_input_objects",
            "action_input_items",
        ):
            conn.execute(f"DELETE FROM {table} WHERE action_id IN ({ph})", old_ids)

        # Delete orphaned requirement groups and their children
        if group_ids:
            gph = ",".join("?" * len(group_ids))
            for table in (
                "group_skill_requirements",
                "group_quest_requirements",
                "group_quest_point_requirements",
                "group_item_requirements",
                "group_diary_requirements",
                "group_region_requirements",
                "group_equipment_requirements",
            ):
                conn.execute(f"DELETE FROM {table} WHERE group_id IN ({gph})", group_ids)
            conn.execute(
                f"DELETE FROM requirement_groups WHERE id IN ({gph})", group_ids,
            )

        conn.execute("DELETE FROM source_actions WHERE source = ?", (source,))
        conn.execute(f"DELETE FROM actions WHERE id IN ({ph})", old_ids)
        return old_ids

    # --- Private ---

    @classmethod
    def _from_row(cls, row: tuple) -> Action:
        return cls(
            id=row[0],
            name=row[1],
            members=bool(row[2]),
            ticks=row[3],
            notes=row[4],
        )
