from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field


@dataclass
class GameVar:
    id: int
    name: str
    var_id: int
    var_type: str
    description: str | None
    content_tags: list[str] = field(default_factory=list)
    functional_tags: list[str] = field(default_factory=list)

    @classmethod
    def _from_row(cls, row: tuple) -> GameVar:
        id_, name, var_id, var_type, description, content_raw, functional_raw = row
        return cls(
            id=id_,
            name=name,
            var_id=var_id,
            var_type=var_type,
            description=description,
            content_tags=json.loads(content_raw) if content_raw else [],
            functional_tags=json.loads(functional_raw) if functional_raw else [],
        )

    _COLS = "id, name, var_id, var_type, description, content_tags, functional_tags"

    @classmethod
    def all(cls, conn: sqlite3.Connection, var_type: str | None = None) -> list[GameVar]:
        if var_type:
            rows = conn.execute(
                f"SELECT {cls._COLS} FROM game_vars WHERE var_type = ? ORDER BY var_id",
                (var_type,),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {cls._COLS} FROM game_vars ORDER BY var_type, var_id"
            ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> list[GameVar]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM game_vars WHERE name = ?",
            (name,),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def search(cls, conn: sqlite3.Connection, name: str) -> list[GameVar]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM game_vars WHERE name LIKE ? ORDER BY var_type, var_id",
            (f"%{name}%",),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def by_var_id(cls, conn: sqlite3.Connection, var_id: int, var_type: str) -> GameVar | None:
        row = conn.execute(
            f"SELECT {cls._COLS} FROM game_vars WHERE var_id = ? AND var_type = ?",
            (var_id, var_type),
        ).fetchone()
        return cls._from_row(row) if row else None
