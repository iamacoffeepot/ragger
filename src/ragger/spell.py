from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ragger.enums import Element, Spellbook


@dataclass
class SpellRune:
    item_id: int
    item_name: str
    quantity: int


def _fetch_runes(conn: sqlite3.Connection, table: str, spell_id: int) -> list[SpellRune]:
    rows = conn.execute(
        f"""SELECT sr.item_id, i.name, sr.quantity
            FROM {table} sr
            JOIN items i ON i.id = sr.item_id
            WHERE sr.spell_id = ?
            ORDER BY i.name""",
        (spell_id,),
    ).fetchall()
    return [SpellRune(item_id=r[0], item_name=r[1], quantity=r[2]) for r in rows]


@dataclass
class CombatSpell:
    id: int
    name: str
    members: bool
    level: int
    spellbook: Spellbook
    experience: float
    speed: int | None
    cooldown: int | None
    element: Element | None
    max_damage: int | None
    description: str | None

    _COLS = "id, name, members, level, spellbook, experience, speed, cooldown, element, max_damage, description"

    @classmethod
    def all(cls, conn: sqlite3.Connection, spellbook: Spellbook | None = None) -> list[CombatSpell]:
        query = f"SELECT {cls._COLS} FROM combat_spells"
        params: list = []
        if spellbook is not None:
            query += " WHERE spellbook = ?"
            params.append(spellbook.value)
        query += " ORDER BY level, name"
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> CombatSpell | None:
        row = conn.execute(
            f"SELECT {cls._COLS} FROM combat_spells WHERE name = ?", (name,)
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def search(cls, conn: sqlite3.Connection, name: str) -> list[CombatSpell]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM combat_spells WHERE name LIKE ? ORDER BY name",
            (f"%{name}%",),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def by_element(cls, conn: sqlite3.Connection, element: Element) -> list[CombatSpell]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM combat_spells WHERE element = ? ORDER BY level",
            (element.value,),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def at_level(cls, conn: sqlite3.Connection, level: int) -> list[CombatSpell]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM combat_spells WHERE level <= ? ORDER BY level",
            (level,),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    def runes(self, conn: sqlite3.Connection) -> list[SpellRune]:
        return _fetch_runes(conn, "combat_spell_runes", self.id)

    @classmethod
    def _from_row(cls, row: tuple) -> CombatSpell:
        return cls(
            id=row[0],
            name=row[1],
            members=bool(row[2]),
            level=row[3],
            spellbook=Spellbook(row[4]),
            experience=row[5],
            speed=row[6],
            cooldown=row[7],
            element=Element(row[8]) if row[8] else None,
            max_damage=row[9],
            description=row[10],
        )


@dataclass
class UtilitySpell:
    id: int
    name: str
    members: bool
    level: int
    spellbook: Spellbook
    experience: float
    speed: int | None
    cooldown: int | None
    description: str | None

    _COLS = "id, name, members, level, spellbook, experience, speed, cooldown, description"

    @classmethod
    def all(cls, conn: sqlite3.Connection, spellbook: Spellbook | None = None) -> list[UtilitySpell]:
        query = f"SELECT {cls._COLS} FROM utility_spells"
        params: list = []
        if spellbook is not None:
            query += " WHERE spellbook = ?"
            params.append(spellbook.value)
        query += " ORDER BY level, name"
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> UtilitySpell | None:
        row = conn.execute(
            f"SELECT {cls._COLS} FROM utility_spells WHERE name = ?", (name,)
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def search(cls, conn: sqlite3.Connection, name: str) -> list[UtilitySpell]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM utility_spells WHERE name LIKE ? ORDER BY name",
            (f"%{name}%",),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def at_level(cls, conn: sqlite3.Connection, level: int) -> list[UtilitySpell]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM utility_spells WHERE level <= ? ORDER BY level",
            (level,),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    def runes(self, conn: sqlite3.Connection) -> list[SpellRune]:
        return _fetch_runes(conn, "utility_spell_runes", self.id)

    @classmethod
    def _from_row(cls, row: tuple) -> UtilitySpell:
        return cls(
            id=row[0],
            name=row[1],
            members=bool(row[2]),
            level=row[3],
            spellbook=Spellbook(row[4]),
            experience=row[5],
            speed=row[6],
            cooldown=row[7],
            description=row[8],
        )


@dataclass
class TeleportSpell:
    id: int
    name: str
    members: bool
    level: int
    spellbook: Spellbook
    experience: float
    speed: int | None
    destination: str | None
    dst_x: int | None
    dst_y: int | None
    lectern: str | None
    description: str | None

    _COLS = "id, name, members, level, spellbook, experience, speed, destination, dst_x, dst_y, lectern, description"

    @classmethod
    def all(cls, conn: sqlite3.Connection, spellbook: Spellbook | None = None) -> list[TeleportSpell]:
        query = f"SELECT {cls._COLS} FROM teleport_spells"
        params: list = []
        if spellbook is not None:
            query += " WHERE spellbook = ?"
            params.append(spellbook.value)
        query += " ORDER BY level, name"
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> TeleportSpell | None:
        row = conn.execute(
            f"SELECT {cls._COLS} FROM teleport_spells WHERE name = ?", (name,)
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def search(cls, conn: sqlite3.Connection, name: str) -> list[TeleportSpell]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM teleport_spells WHERE name LIKE ? ORDER BY name",
            (f"%{name}%",),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def at_level(cls, conn: sqlite3.Connection, level: int) -> list[TeleportSpell]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM teleport_spells WHERE level <= ? ORDER BY level",
            (level,),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    def runes(self, conn: sqlite3.Connection) -> list[SpellRune]:
        return _fetch_runes(conn, "teleport_spell_runes", self.id)

    @classmethod
    def _from_row(cls, row: tuple) -> TeleportSpell:
        return cls(
            id=row[0],
            name=row[1],
            members=bool(row[2]),
            level=row[3],
            spellbook=Spellbook(row[4]),
            experience=row[5],
            speed=row[6],
            destination=row[7],
            dst_x=row[8],
            dst_y=row[9],
            lectern=row[10],
            description=row[11],
        )
