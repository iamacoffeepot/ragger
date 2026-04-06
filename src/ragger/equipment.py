from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ragger.enums import CombatStyle, EquipmentSlot


@dataclass
class Equipment:
    id: int
    name: str
    version: str | None
    item_id: int | None
    slot: EquipmentSlot | None
    two_handed: bool
    members: bool | None
    tradeable: bool | None
    weight: float | None
    game_id: int | None
    examine: str | None
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
        "id, name, version, item_id, slot, two_handed, members, tradeable, weight, game_id, examine, "
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

    @classmethod
    def _from_row(cls, row: tuple) -> Equipment:
        return cls(
            id=row[0],
            name=row[1],
            version=row[2],
            item_id=row[3],
            slot=EquipmentSlot.from_label(row[4]) if row[4] else None,
            two_handed=bool(row[5]),
            members=bool(row[6]) if row[6] is not None else None,
            tradeable=bool(row[7]) if row[7] is not None else None,
            weight=row[8],
            game_id=row[9],
            examine=row[10],
            attack_stab=row[11],
            attack_slash=row[12],
            attack_crush=row[13],
            attack_magic=row[14],
            attack_ranged=row[15],
            defence_stab=row[16],
            defence_slash=row[17],
            defence_crush=row[18],
            defence_magic=row[19],
            defence_ranged=row[20],
            melee_strength=row[21],
            ranged_strength=row[22],
            magic_damage=row[23],
            prayer=row[24],
            speed=row[25],
            attack_range=row[26],
            combat_style=CombatStyle.from_label(row[27]) if row[27] else None,
        )
