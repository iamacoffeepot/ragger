from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ragger.enums import Skill


@dataclass
class RecipeSkill:
    skill: Skill
    level: int
    xp: float
    boostable: bool | None


@dataclass
class RecipeInput:
    item_id: int | None
    item_name: str
    quantity: int


@dataclass
class RecipeOutput:
    item_id: int | None
    item_name: str
    quantity: int


@dataclass
class RecipeTool:
    tool_group: int
    item_id: int | None
    item_name: str


@dataclass
class Recipe:
    id: int
    name: str
    members: bool
    ticks: int | None
    notes: str | None
    facilities: str | None

    _COLS = "id, name, members, ticks, notes, facilities"

    @classmethod
    def all(cls, conn: sqlite3.Connection) -> list[Recipe]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM recipes ORDER BY id",
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def by_skill(cls, conn: sqlite3.Connection, skill: Skill) -> list[Recipe]:
        rows = conn.execute(
            f"""SELECT DISTINCT r.{cls._COLS.replace(', ', ', r.')}
                FROM recipes r
                JOIN recipe_skills rs ON rs.recipe_id = r.id
                WHERE rs.skill = ?
                ORDER BY rs.level, r.id""",
            (skill.value,),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def for_item(cls, conn: sqlite3.Connection, item_name: str) -> list[Recipe]:
        """Find recipes that produce a given item."""
        rows = conn.execute(
            f"""SELECT r.{cls._COLS.replace(', ', ', r.')}
                FROM recipes r
                JOIN recipe_outputs ro ON ro.recipe_id = r.id
                WHERE ro.item_name = ?
                ORDER BY r.id""",
            (item_name,),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def using(cls, conn: sqlite3.Connection, item_name: str) -> list[Recipe]:
        """Find recipes that consume a given item as input."""
        rows = conn.execute(
            f"""SELECT r.{cls._COLS.replace(', ', ', r.')}
                FROM recipes r
                JOIN recipe_inputs ri ON ri.recipe_id = r.id
                WHERE ri.item_name = ?
                ORDER BY r.id""",
            (item_name,),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def at_facility(cls, conn: sqlite3.Connection, facility: str) -> list[Recipe]:
        """Find recipes that require a given facility."""
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM recipes WHERE facilities = ? ORDER BY id",
            (facility,),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    def skills(self, conn: sqlite3.Connection) -> list[RecipeSkill]:
        rows = conn.execute(
            "SELECT skill, level, xp, boostable FROM recipe_skills WHERE recipe_id = ? ORDER BY skill",
            (self.id,),
        ).fetchall()
        return [
            RecipeSkill(
                skill=Skill(row[0]),
                level=row[1],
                xp=row[2],
                boostable=bool(row[3]) if row[3] is not None else None,
            )
            for row in rows
        ]

    def inputs(self, conn: sqlite3.Connection) -> list[RecipeInput]:
        rows = conn.execute(
            "SELECT item_id, item_name, quantity FROM recipe_inputs WHERE recipe_id = ? ORDER BY item_name",
            (self.id,),
        ).fetchall()
        return [RecipeInput(item_id=row[0], item_name=row[1], quantity=row[2]) for row in rows]

    def outputs(self, conn: sqlite3.Connection) -> list[RecipeOutput]:
        rows = conn.execute(
            "SELECT item_id, item_name, quantity FROM recipe_outputs WHERE recipe_id = ? ORDER BY item_name",
            (self.id,),
        ).fetchall()
        return [RecipeOutput(item_id=row[0], item_name=row[1], quantity=row[2]) for row in rows]

    def tools(self, conn: sqlite3.Connection) -> list[RecipeTool]:
        rows = conn.execute(
            "SELECT tool_group, item_id, item_name FROM recipe_tools WHERE recipe_id = ? ORDER BY tool_group, item_name",
            (self.id,),
        ).fetchall()
        return [RecipeTool(tool_group=row[0], item_id=row[1], item_name=row[2]) for row in rows]

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> list[Recipe]:
        """Find recipes by name (may have multiple methods for same output)."""
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM recipes WHERE name = ? ORDER BY id",
            (name,),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def search(cls, conn: sqlite3.Connection, name: str) -> list[Recipe]:
        """Find recipes whose name matches a partial string."""
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM recipes WHERE name LIKE ? ORDER BY name, id",
            (f"%{name}%",),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def _from_row(cls, row: tuple) -> Recipe:
        return cls(
            id=row[0],
            name=row[1],
            members=bool(row[2]),
            ticks=row[3],
            notes=row[4],
            facilities=row[5],
        )
