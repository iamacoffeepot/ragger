"""DialogueTag: an entity tag attached to a dialogue node."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ragger.dialogue.dialogue_helpers import TAG_COLUMNS
from ragger.enums import DialogueEntityType


@dataclass
class DialogueTag:
    id: int
    node_id: int
    entity_type: DialogueEntityType
    entity_name: str
    entity_id: int | None

    @classmethod
    def _from_row(cls, row: tuple) -> DialogueTag:
        return cls(
            id=row[0],
            node_id=row[1],
            entity_type=DialogueEntityType(row[2]),
            entity_name=row[3],
            entity_id=row[4],
        )

    @classmethod
    def by_node(cls, conn: sqlite3.Connection, node_id: int) -> list[DialogueTag]:
        rows = conn.execute(
            f"SELECT {TAG_COLUMNS} FROM dialogue_tags WHERE node_id = ?",
            (node_id,),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def by_entity(
        cls, conn: sqlite3.Connection, entity_type: DialogueEntityType, entity_name: str
    ) -> list[DialogueTag]:
        rows = conn.execute(
            f"""SELECT {TAG_COLUMNS}
                FROM dialogue_tags WHERE entity_type = ? AND entity_name = ?""",
            (entity_type, entity_name),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def by_entity_type(cls, conn: sqlite3.Connection, entity_type: DialogueEntityType) -> list[DialogueTag]:
        rows = conn.execute(
            f"SELECT {TAG_COLUMNS} FROM dialogue_tags WHERE entity_type = ?",
            (entity_type,),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def search(cls, conn: sqlite3.Connection, entity_name: str) -> list[DialogueTag]:
        rows = conn.execute(
            f"""SELECT {TAG_COLUMNS}
                FROM dialogue_tags WHERE entity_name LIKE ?""",
            (f"%{entity_name}%",),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    def node(self, conn: sqlite3.Connection):
        from ragger.dialogue.dialogue_node import DialogueNode

        return DialogueNode.by_id(conn, self.node_id)
