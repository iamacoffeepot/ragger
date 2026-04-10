from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ragger.enums import Element, Spellbook
from ragger.mcp_registry import mcp_tool


@dataclass
class SpellRune:
    item_id: int
    item_name: str
    quantity: int

    def asdict(self) -> dict:
        return {"item_id": self.item_id, "item_name": self.item_name, "quantity": self.quantity}


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

    def asdict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "members": self.members,
            "level": self.level, "spellbook": self.spellbook.value,
            "experience": self.experience, "speed": self.speed,
            "cooldown": self.cooldown, "element": self.element.value if self.element else None,
            "max_damage": self.max_damage, "description": self.description,
        }

    @classmethod
    def by_id(cls, conn: sqlite3.Connection, id: int) -> CombatSpell | None:
        row = conn.execute(f"SELECT {cls._COLS} FROM combat_spells WHERE id = ?", (id,)).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    @mcp_tool(name="CombatSpellAll", description="List combat spells, optionally filtered by spellbook (NORMAL, ANCIENT, LUNAR). Returns level, element, max_damage, experience, speed.")
    def all(cls, conn: sqlite3.Connection, spellbook: Spellbook | None = None) -> list[CombatSpell]:
        query = f"SELECT {cls._COLS} FROM combat_spells"
        params: list = []
        if spellbook is not None:
            query += " WHERE spellbook = ?"
            params.append(spellbook.value)
        query += " ORDER BY level, name"
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    @mcp_tool(name="CombatSpellByName", description="Find a combat spell by exact name (e.g. 'Fire Blast', 'Ice Barrage'). Returns level, element, max_damage, spellbook, experience, speed.")
    def by_name(cls, conn: sqlite3.Connection, name: str) -> CombatSpell | None:
        row = conn.execute(
            f"SELECT {cls._COLS} FROM combat_spells WHERE name = ?", (name,)
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    @mcp_tool(name="CombatSpellSearch", description="Search combat spells by partial name match (LIKE %%name%%).")
    def search(cls, conn: sqlite3.Connection, name: str) -> list[CombatSpell]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM combat_spells WHERE name LIKE ? ORDER BY name",
            (f"%{name}%",),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    @mcp_tool(name="CombatSpellByElement", description="Find combat spells by element (AIR, WATER, EARTH, FIRE). Ordered by level.")
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

    @mcp_tool(name="CombatSpellRunes", description="Rune cost for a combat spell. Returns item_name and quantity for each rune. Pass the spell id from CombatSpellByName.")
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

    def asdict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "members": self.members,
            "level": self.level, "spellbook": self.spellbook.value,
            "experience": self.experience, "speed": self.speed,
            "cooldown": self.cooldown, "description": self.description,
        }

    @classmethod
    def by_id(cls, conn: sqlite3.Connection, id: int) -> UtilitySpell | None:
        row = conn.execute(f"SELECT {cls._COLS} FROM utility_spells WHERE id = ?", (id,)).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    @mcp_tool(name="UtilitySpellAll", description="List utility spells (non-combat, non-teleport), optionally filtered by spellbook. Includes alchemy, enchantment, superheat, etc.")
    def all(cls, conn: sqlite3.Connection, spellbook: Spellbook | None = None) -> list[UtilitySpell]:
        query = f"SELECT {cls._COLS} FROM utility_spells"
        params: list = []
        if spellbook is not None:
            query += " WHERE spellbook = ?"
            params.append(spellbook.value)
        query += " ORDER BY level, name"
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    @mcp_tool(name="UtilitySpellByName", description="Find a utility spell by exact name (e.g. 'High Level Alchemy', 'Superheat Item'). Returns level, spellbook, experience.")
    def by_name(cls, conn: sqlite3.Connection, name: str) -> UtilitySpell | None:
        row = conn.execute(
            f"SELECT {cls._COLS} FROM utility_spells WHERE name = ?", (name,)
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    @mcp_tool(name="UtilitySpellSearch", description="Search utility spells by partial name match (LIKE %%name%%).")
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

    @mcp_tool(name="UtilitySpellRunes", description="Rune cost for a utility spell. Returns item_name and quantity. Pass the spell id from UtilitySpellByName.")
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

    def asdict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "members": self.members,
            "level": self.level, "spellbook": self.spellbook.value,
            "experience": self.experience, "speed": self.speed,
            "destination": self.destination, "dst_x": self.dst_x, "dst_y": self.dst_y,
            "lectern": self.lectern, "description": self.description,
        }

    @classmethod
    def by_id(cls, conn: sqlite3.Connection, id: int) -> TeleportSpell | None:
        row = conn.execute(f"SELECT {cls._COLS} FROM teleport_spells WHERE id = ?", (id,)).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    @mcp_tool(name="TeleportSpellAll", description="List teleport spells, optionally filtered by spellbook. Returns destination name, dst_x/dst_y coordinates, and lectern (if tablet-craftable).")
    def all(cls, conn: sqlite3.Connection, spellbook: Spellbook | None = None) -> list[TeleportSpell]:
        query = f"SELECT {cls._COLS} FROM teleport_spells"
        params: list = []
        if spellbook is not None:
            query += " WHERE spellbook = ?"
            params.append(spellbook.value)
        query += " ORDER BY level, name"
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    @mcp_tool(name="TeleportSpellByName", description="Find a teleport spell by exact name (e.g. 'Varrock Teleport', 'Kharyrll Teleport'). Returns destination, coordinates, level, rune cost.")
    def by_name(cls, conn: sqlite3.Connection, name: str) -> TeleportSpell | None:
        row = conn.execute(
            f"SELECT {cls._COLS} FROM teleport_spells WHERE name = ?", (name,)
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    @mcp_tool(name="TeleportSpellSearch", description="Search teleport spells by partial name match (LIKE %%name%%). Use to find teleports to a destination.")
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

    @mcp_tool(name="TeleportSpellRunes", description="Rune cost for a teleport spell. Returns item_name and quantity. Pass the spell id from TeleportSpellByName.")
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
