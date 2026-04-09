"""DialoguePage: a wiki transcript page record."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ragger.dialogue.dialogue_helpers import NODE_COLUMNS, PAGE_COLUMNS
from ragger.enums import DialoguePageType


@dataclass
class DialoguePage:
    id: int
    title: str
    page_type: DialoguePageType | None

    @classmethod
    def _from_row(cls, row: tuple) -> DialoguePage:
        return cls(
            id=row[0],
            title=row[1],
            page_type=DialoguePageType(row[2]) if row[2] is not None else None,
        )

    @classmethod
    def all(cls, conn: sqlite3.Connection, page_type: DialoguePageType | None = None) -> list[DialoguePage]:
        query = f"SELECT {PAGE_COLUMNS} FROM dialogue_pages"
        params: list = []
        if page_type is not None:
            query += " WHERE page_type = ?"
            params.append(page_type)
        query += " ORDER BY title"
        return [cls._from_row(r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    def by_title(cls, conn: sqlite3.Connection, title: str) -> DialoguePage | None:
        row = conn.execute(
            f"SELECT {PAGE_COLUMNS} FROM dialogue_pages WHERE title = ?", (title,)
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def search(cls, conn: sqlite3.Connection, title: str) -> list[DialoguePage]:
        rows = conn.execute(
            f"SELECT {PAGE_COLUMNS} FROM dialogue_pages WHERE title LIKE ? ORDER BY title",
            (f"%{title}%",),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    def nodes(self, conn: sqlite3.Connection):
        from ragger.dialogue.dialogue_node import DialogueNode

        return DialogueNode.by_page(conn, self.id)

    def roots(self, conn: sqlite3.Connection):
        """Return only the top-level nodes (no parent)."""
        from ragger.dialogue.dialogue_node import DialogueNode

        rows = conn.execute(
            f"""SELECT {NODE_COLUMNS}
                FROM dialogue_nodes WHERE page_id = ? AND parent_id IS NULL
                ORDER BY sort_order""",
            (self.id,),
        ).fetchall()
        return [DialogueNode._from_row(r) for r in rows]

    def instructions(self, conn: sqlite3.Connection):
        from ragger.dialogue.dialogue_instruction import Instruction

        return Instruction.for_page(conn, self.id)

    def render(self, conn: sqlite3.Connection, section: str | None = None) -> str:
        """Render the dialogue tree as indented text.

        Each line is prefixed with a zero-padded node ID and a colon. If
        section is given, only nodes in that section are included and the
        section header is omitted. ACTION nodes that resolve to another
        node via ``continue_target_id`` are rendered as ``-> #<target_id>``.
        """
        from ragger.dialogue.dialogue_node import DialogueNode

        if section is not None:
            nodes = DialogueNode.by_section(conn, self.id, section)
        else:
            nodes = self.nodes(conn)

        lines: list[str] = []
        current_section: str | None = None

        for node in nodes:
            if section is None and node.section != current_section:
                current_section = node.section
                if current_section:
                    if lines:
                        lines.append("")
                    lines.append(f"== {current_section} ==")

            if node.continue_target_id is not None:
                indent = "  " * (node.depth - 1)
                lines.append(f"{node.id:06d}: {indent}-> #{node.continue_target_id:06d}")
            else:
                lines.append(node.render())

        return "\n".join(lines)

    def sections(self, conn: sqlite3.Connection) -> list[str]:
        """Return distinct section headings in order."""
        rows = conn.execute(
            """SELECT DISTINCT section FROM dialogue_nodes
               WHERE page_id = ? AND section IS NOT NULL
               ORDER BY sort_order""",
            (self.id,),
        ).fetchall()
        return [r[0] for r in rows]
