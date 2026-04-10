from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from ragger.enums import ContentCategory, FunctionalTag, VariableType


@dataclass
class ContentTag:
    """A parsed content tag like quest:troll_stronghold."""

    category: ContentCategory
    name: str

    def __str__(self) -> str:
        return f"{self.category.value}:{self.name}"

    @classmethod
    def parse(cls, raw: str) -> ContentTag | None:
        if ":" not in raw:
            return None
        cat_str, name = raw.split(":", 1)
        try:
            return cls(category=ContentCategory.from_label(cat_str), name=name)
        except ValueError:
            return None

    @classmethod
    def parse_list(cls, raw_list: list[str]) -> list[ContentTag]:
        tags = []
        for raw in raw_list:
            tag = cls.parse(raw)
            if tag:
                tags.append(tag)
        return tags


@dataclass
class VariableValue:
    """A single annotated value for a game variable (e.g. quest stage)."""

    var_type: VariableType
    var_id: int
    value: int
    label: str


@dataclass
class GameVariable:
    id: int
    name: str
    var_id: int
    var_type: VariableType
    description: str | None
    content_tags: list[ContentTag] = field(default_factory=list)
    functional_tags: list[FunctionalTag] = field(default_factory=list)
    wiki_name: str | None = None
    wiki_content: str | None = None
    var_class: str | None = None

    @classmethod
    def _from_row(cls, row: tuple) -> GameVariable:
        id_, name, var_id, var_type, description, content_raw, functional_raw, wiki_name, wiki_content, var_class = row
        raw_content = json.loads(content_raw) if content_raw else []
        raw_functional = json.loads(functional_raw) if functional_raw else []
        return cls(
            id=id_,
            name=name,
            var_id=var_id,
            var_type=VariableType(var_type),
            description=description,
            content_tags=ContentTag.parse_list(raw_content),
            functional_tags=_parse_functional(raw_functional),
            wiki_name=wiki_name,
            wiki_content=wiki_content,
            var_class=var_class,
        )

    _COLS = "id, name, var_id, var_type, description, content_tags, functional_tags, wiki_name, wiki_content, var_class"

    @classmethod
    def all(cls, conn: sqlite3.Connection, var_type: VariableType | None = None) -> list[GameVariable]:
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
    def by_name(cls, conn: sqlite3.Connection, name: str) -> GameVariable | None:
        row = conn.execute(
            f"SELECT {cls._COLS} FROM game_vars WHERE name = ? LIMIT 1",
            (name,),
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def all_by_name(cls, conn: sqlite3.Connection, name: str) -> list[GameVariable]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM game_vars WHERE name = ?",
            (name,),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def search(cls, conn: sqlite3.Connection, name: str) -> list[GameVariable]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM game_vars WHERE name LIKE ? ORDER BY var_type, var_id",
            (f"%{name}%",),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def by_var_id(cls, conn: sqlite3.Connection, var_id: int, var_type: VariableType) -> GameVariable | None:
        row = conn.execute(
            f"SELECT {cls._COLS} FROM game_vars WHERE var_id = ? AND var_type = ?",
            (var_id, var_type),
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def by_content_tag(
        cls, conn: sqlite3.Connection, tag: ContentCategory | str, name: str | None = None, var_type: VariableType | None = None,
    ) -> list[GameVariable]:
        """Find vars by content tag.

        Accepts either:
          - by_content_tag(conn, ContentCategory.QUEST, "dragon_slayer_i")
          - by_content_tag(conn, "quest:dragon_slayer_i")  (legacy string form)
          - by_content_tag(conn, ContentCategory.QUEST)  (all vars in category)
          - by_content_tag(conn, "quest")  (all vars in category)
        """
        if isinstance(tag, ContentCategory):
            tag_str = f"{tag.value}:{name}" if name else tag.value
        else:
            tag_str = tag
        if ":" in tag_str:
            pattern = f'%"{tag_str}"%'
        else:
            pattern = f'%"{tag_str}:%'
        query = f"SELECT {cls._COLS} FROM game_vars WHERE content_tags LIKE ?"
        params: list = [pattern]
        if var_type:
            query += " AND var_type = ?"
            params.append(var_type)
        query += " ORDER BY var_type, var_id"
        rows = conn.execute(query, params).fetchall()
        return [cls._from_row(row) for row in rows]

    def values(self, conn: sqlite3.Connection) -> list[VariableValue]:
        """Return annotated values for this var (e.g. quest stage descriptions)."""
        rows = conn.execute(
            "SELECT var_type, var_id, value, label FROM game_var_values WHERE var_type = ? AND var_id = ? ORDER BY value",
            (self.var_type, self.var_id),
        ).fetchall()
        return [VariableValue(VariableType(r[0]), r[1], r[2], r[3]) for r in rows]

    @classmethod
    def by_functional_tag(
        cls, conn: sqlite3.Connection, tag: FunctionalTag | str, var_type: VariableType | None = None,
    ) -> list[GameVariable]:
        """Find vars matching a functional tag like FunctionalTag.TIMER or 'timer'."""
        value = tag.value if isinstance(tag, FunctionalTag) else tag
        pattern = f'%"{value}"%'
        query = f"SELECT {cls._COLS} FROM game_vars WHERE functional_tags LIKE ?"
        params: list = [pattern]
        if var_type:
            query += " AND var_type = ?"
            params.append(var_type)
        query += " ORDER BY var_type, var_id"
        rows = conn.execute(query, params).fetchall()
        return [cls._from_row(row) for row in rows]


def _parse_functional(raw: list[str]) -> list[FunctionalTag]:
    tags = []
    for s in raw:
        try:
            tags.append(FunctionalTag.from_label(s))
        except ValueError:
            pass
    return tags


