from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ragger.enums import CombatStyle, ComparisonOperator, EquipmentSlot, Skill
from ragger.requirements import (
    GroupQuestRequirement,
    GroupSkillRequirement,
    RequirementGroup,
)


@dataclass
class Equipment:
    id: int
    name: str
    version: str | None
    item_id: int | None
    slot: EquipmentSlot | None
    two_handed: bool
    attack_stab: int | None
    attack_slash: int | None
    attack_crush: int | None
    attack_magic: int | None
    attack_ranged: int | None
    defence_stab: int | None
    defence_slash: int | None
    defence_crush: int | None
    defence_magic: int | None
    defence_ranged: int | None
    melee_strength: int | None
    ranged_strength: int | None
    magic_damage: int | None
    prayer: int | None
    speed: int | None
    attack_range: int | None
    combat_style: CombatStyle | None

    _COLS = (
        "id, name, version, item_id, slot, two_handed, "
        "attack_stab, attack_slash, attack_crush, attack_magic, attack_ranged, "
        "defence_stab, defence_slash, defence_crush, defence_magic, defence_ranged, "
        "melee_strength, ranged_strength, magic_damage, prayer, "
        "speed, attack_range, combat_style"
    )

    @classmethod
    def all(
        cls,
        conn: sqlite3.Connection,
        slot: EquipmentSlot | None = None,
    ) -> list[Equipment]:
        if slot is not None:
            rows = conn.execute(
                f"SELECT {cls._COLS} FROM equipment WHERE slot = ? ORDER BY name, version",
                (slot.value,),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {cls._COLS} FROM equipment ORDER BY name, version",
            ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def by_name(
        cls,
        conn: sqlite3.Connection,
        name: str,
        version: str | None = None,
    ) -> Equipment | None:
        if version is not None:
            row = conn.execute(
                f"SELECT {cls._COLS} FROM equipment WHERE name = ? AND version = ?",
                (name, version),
            ).fetchone()
        else:
            row = conn.execute(
                f"SELECT {cls._COLS} FROM equipment WHERE name = ? ORDER BY version LIMIT 1",
                (name,),
            ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def by_slot(cls, conn: sqlite3.Connection, slot: EquipmentSlot) -> list[Equipment]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM equipment WHERE slot = ? ORDER BY name, version",
            (slot.value,),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def search(cls, conn: sqlite3.Connection, name: str) -> list[Equipment]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM equipment WHERE name LIKE ? ORDER BY name, version",
            (f"%{name}%",),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def for_item(cls, conn: sqlite3.Connection, item_id: int) -> list[Equipment]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM equipment WHERE item_id = ? ORDER BY name, version",
            (item_id,),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    def requirement_groups(self, conn: sqlite3.Connection) -> list[RequirementGroup]:
        return RequirementGroup.for_equipment(conn, self.id)

    def skill_requirements(self, conn: sqlite3.Connection) -> list[GroupSkillRequirement]:
        rows = conn.execute(
            """
            SELECT gsr.id, gsr.group_id, gsr.skill, gsr.level, gsr.boostable, gsr.operator
            FROM group_skill_requirements gsr
            JOIN equipment_requirement_groups erg ON erg.group_id = gsr.group_id
            WHERE erg.equipment_id = ?
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
            JOIN equipment_requirement_groups erg ON erg.group_id = gqr.group_id
            WHERE erg.equipment_id = ?
            """,
            (self.id,),
        ).fetchall()
        return [GroupQuestRequirement(r[0], r[1], r[2], bool(r[3])) for r in rows]

    @classmethod
    def _from_row(cls, row: tuple) -> Equipment:
        return cls(
            id=row[0],
            name=row[1],
            version=row[2],
            item_id=row[3],
            slot=EquipmentSlot.from_label(row[4]) if row[4] else None,
            two_handed=bool(row[5]),
            attack_stab=row[6],
            attack_slash=row[7],
            attack_crush=row[8],
            attack_magic=row[9],
            attack_ranged=row[10],
            defence_stab=row[11],
            defence_slash=row[12],
            defence_crush=row[13],
            defence_magic=row[14],
            defence_ranged=row[15],
            melee_strength=row[16],
            ranged_strength=row[17],
            magic_damage=row[18],
            prayer=row[19],
            speed=row[20],
            attack_range=row[21],
            combat_style=CombatStyle.from_label(row[22]) if row[22] else None,
        )
