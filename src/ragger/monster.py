from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ragger.enums import ComparisonOperator, ContentCategory, Immunity, Region, Skill
from ragger.game_variable import GameVariable
from ragger.requirements import (
    GroupQuestRequirement,
    GroupSkillRequirement,
    RequirementGroup,
)
from ragger.mcp_registry import mcp_tool
from ragger.utils import snake_case


@dataclass
class MonsterLocation:
    id: int
    monster_id: int
    location: str | None
    x: int | None
    y: int | None
    region: Region | None

    def asdict(self) -> dict:
        return {"id": self.id, "monster_id": self.monster_id, "location": self.location, "x": self.x, "y": self.y, "region": self.region.value if self.region else None}


@dataclass
class MonsterDrop:
    id: int
    monster_id: int
    item_name: str
    quantity: str | None
    rarity: str | None

    def asdict(self) -> dict:
        return {"id": self.id, "monster_id": self.monster_id, "item_name": self.item_name, "quantity": self.quantity, "rarity": self.rarity}


@dataclass
class Monster:
    id: int
    name: str
    version: str | None
    combat_level: int | None
    hitpoints: int | None
    attack_speed: int | None
    max_hit: str | None
    attack_style: str | None
    aggressive: bool | None
    size: int | None
    respawn: int | None
    attack_level: int | None
    strength_level: int | None
    defence_level: int | None
    magic_level: int | None
    ranged_level: int | None
    attack_bonus: int | None
    strength_bonus: int | None
    magic_attack: int | None
    magic_strength: int | None
    ranged_attack: int | None
    ranged_strength: int | None
    defensive_stab: int | None
    defensive_slash: int | None
    defensive_crush: int | None
    defensive_magic: int | None
    defensive_light_ranged: int | None
    defensive_standard_ranged: int | None
    defensive_heavy_ranged: int | None
    elemental_weakness_type: str | None
    elemental_weakness_percent: int | None
    immunities: int
    slayer_xp: float | None
    slayer_category: str | None
    slayer_assigned_by: str | None
    attributes: str | None
    examine: str | None
    members: bool | None

    _COLS = (
        "id, name, version, combat_level, hitpoints, attack_speed, max_hit, "
        "attack_style, aggressive, size, respawn, "
        "attack_level, strength_level, defence_level, magic_level, ranged_level, "
        "attack_bonus, strength_bonus, magic_attack, magic_strength, ranged_attack, ranged_strength, "
        "defensive_stab, defensive_slash, defensive_crush, defensive_magic, "
        "defensive_light_ranged, defensive_standard_ranged, defensive_heavy_ranged, "
        "elemental_weakness_type, elemental_weakness_percent, immunities, "
        "slayer_xp, slayer_category, slayer_assigned_by, attributes, examine, members"
    )

    @classmethod
    @mcp_tool(
        name="MonsterDetails",
        description="Full monster details by id. Returns combat stats, drop table (item name, quantity, rarity), spawn locations (location name, coordinates, region), and slayer info. Get the id from MonsterByName or MonsterSearch first.",
    )
    def details(cls, conn: sqlite3.Connection, id: int) -> dict | None:
        monster = cls.by_id(conn, id)
        if not monster:
            return None
        return {
            **monster.asdict(),
            "drops": [d.asdict() for d in monster.drops(conn)],
            "locations": [l.asdict() for l in monster.locations(conn)],
        }

    def asdict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "version": self.version,
            "combat_level": self.combat_level, "hitpoints": self.hitpoints,
            "attack_speed": self.attack_speed, "max_hit": self.max_hit,
            "attack_style": self.attack_style, "aggressive": self.aggressive,
            "size": self.size, "slayer_xp": self.slayer_xp,
            "slayer_category": self.slayer_category, "examine": self.examine,
            "members": self.members,
        }

    @classmethod
    def by_id(cls, conn: sqlite3.Connection, id: int) -> Monster | None:
        row = conn.execute(f"SELECT {cls._COLS} FROM monsters WHERE id = ?", (id,)).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    @mcp_tool(name="MonsterAll", description="List all monsters, optionally filtered by region. Returns combat_level, hitpoints, attack_speed, slayer info, and examine text. Large result set — prefer MonsterSearch or MonsterByName.")
    def all(
        cls,
        conn: sqlite3.Connection,
        region: Region | None = None,
    ) -> list[Monster]:
        if region is not None:
            query = f"""
                SELECT DISTINCT m.{cls._COLS.replace(', ', ', m.')}
                FROM monsters m
                JOIN monster_locations ml ON ml.monster_id = m.id
                WHERE ml.region = ?
                ORDER BY m.name, m.version
            """
            rows = conn.execute(query, (region.value,)).fetchall()
        else:
            rows = conn.execute(f"SELECT {cls._COLS} FROM monsters ORDER BY name, version").fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    @mcp_tool(name="MonsterByName", description="Find a monster by exact name (e.g. 'Goblin', 'King Black Dragon'). Returns combat stats, hitpoints, attack style, slayer XP/category, and examine text. Version disambiguates multi-form monsters. Without version, returns lowest combat level variant.")
    def by_name(cls, conn: sqlite3.Connection, name: str, version: str | None = None) -> Monster | None:
        if version is not None:
            row = conn.execute(
                f"SELECT {cls._COLS} FROM monsters WHERE name = ? AND version = ?",
                (name, version),
            ).fetchone()
        else:
            row = conn.execute(
                f"SELECT {cls._COLS} FROM monsters WHERE name = ? ORDER BY combat_level LIMIT 1",
                (name,),
            ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    @mcp_tool(name="MonsterBySlayerCategory", description="Find monsters by slayer assignment category (e.g. 'Aberrant spectres', 'Black dragons', 'Gargoyles'). Returns all monsters assignable under that category.")
    def by_slayer_category(cls, conn: sqlite3.Connection, category: str) -> list[Monster]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM monsters WHERE slayer_category = ? ORDER BY name, version",
            (category,),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    @mcp_tool(name="MonsterSearch", description="Search monsters by partial name match (LIKE %%name%%). Use when the exact name is unknown.")
    def search(cls, conn: sqlite3.Connection, name: str) -> list[Monster]:
        """Search monsters by partial name match."""
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM monsters WHERE name LIKE ? ORDER BY name, version",
            (f"%{name}%",),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def _from_row(cls, row: tuple) -> Monster:
        return cls(
            id=row[0],
            name=row[1],
            version=row[2],
            combat_level=row[3],
            hitpoints=row[4],
            attack_speed=row[5],
            max_hit=row[6],
            attack_style=row[7],
            aggressive=bool(row[8]) if row[8] is not None else None,
            size=row[9],
            respawn=row[10],
            attack_level=row[11],
            strength_level=row[12],
            defence_level=row[13],
            magic_level=row[14],
            ranged_level=row[15],
            attack_bonus=row[16],
            strength_bonus=row[17],
            magic_attack=row[18],
            magic_strength=row[19],
            ranged_attack=row[20],
            ranged_strength=row[21],
            defensive_stab=row[22],
            defensive_slash=row[23],
            defensive_crush=row[24],
            defensive_magic=row[25],
            defensive_light_ranged=row[26],
            defensive_standard_ranged=row[27],
            defensive_heavy_ranged=row[28],
            elemental_weakness_type=row[29],
            elemental_weakness_percent=row[30],
            immunities=row[31],
            slayer_xp=row[32],
            slayer_category=row[33],
            slayer_assigned_by=row[34],
            attributes=row[35],
            examine=row[36],
            members=bool(row[37]) if row[37] is not None else None,
        )

    def has_immunity(self, immunity: Immunity) -> bool:
        return bool(self.immunities & immunity.mask)

    def immunity_list(self) -> list[Immunity]:
        return [i for i in Immunity if self.immunities & i.mask]

    def locations(self, conn: sqlite3.Connection) -> list[MonsterLocation]:
        rows = conn.execute(
            "SELECT id, monster_id, location, x, y, region FROM monster_locations WHERE monster_id = ? ORDER BY location",
            (self.id,),
        ).fetchall()
        return [MonsterLocation(
            id=r[0], monster_id=r[1], location=r[2],
            x=r[3], y=r[4],
            region=Region(r[5]) if r[5] is not None else None,
        ) for r in rows]

    def drops(self, conn: sqlite3.Connection) -> list[MonsterDrop]:
        rows = conn.execute(
            "SELECT id, monster_id, item_name, quantity, rarity FROM monster_drops WHERE monster_id = ? ORDER BY id",
            (self.id,),
        ).fetchall()
        return [MonsterDrop(*r) for r in rows]

    def drops_by_name(self, conn: sqlite3.Connection, item_name: str) -> list[MonsterDrop]:
        rows = conn.execute(
            "SELECT id, monster_id, item_name, quantity, rarity FROM monster_drops WHERE monster_id = ? AND item_name = ?",
            (self.id, item_name),
        ).fetchall()
        return [MonsterDrop(*r) for r in rows]

    def requirement_groups(self, conn: sqlite3.Connection) -> list[RequirementGroup]:
        return RequirementGroup.for_monster(conn, self.id)

    def skill_requirements(self, conn: sqlite3.Connection) -> list[GroupSkillRequirement]:
        rows = conn.execute(
            """
            SELECT gsr.id, gsr.group_id, gsr.skill, gsr.level, gsr.boostable, gsr.operator
            FROM group_skill_requirements gsr
            JOIN monster_requirement_groups mrg ON mrg.group_id = gsr.group_id
            WHERE mrg.monster_id = ?
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
            JOIN monster_requirement_groups mrg ON mrg.group_id = gqr.group_id
            WHERE mrg.monster_id = ?
            """,
            (self.id,),
        ).fetchall()
        return [GroupQuestRequirement(r[0], r[1], r[2], bool(r[3])) for r in rows]

    def game_vars(self, conn: sqlite3.Connection) -> list[GameVariable]:
        return GameVariable.by_content_tag(conn, ContentCategory.NPC, snake_case(self.name))
