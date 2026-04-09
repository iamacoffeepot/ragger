"""DialogueNode: a single node in a dialogue tree."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ragger.dialogue.dialogue_helpers import NODE_COLUMNS, PAGE_COLUMNS
from ragger.enums import DialogueNodeType


@dataclass
class DialogueNode:
    id: int
    page_id: int
    parent_id: int | None
    sort_order: int
    depth: int
    node_type: DialogueNodeType
    speaker: str | None
    text: str | None
    section: str | None
    continue_target_id: int | None = None

    @classmethod
    def by_page(cls, conn: sqlite3.Connection, page_id: int) -> list[DialogueNode]:
        rows = conn.execute(
            f"""SELECT {NODE_COLUMNS}
                FROM dialogue_nodes WHERE page_id = ? ORDER BY sort_order""",
            (page_id,),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def by_id(cls, conn: sqlite3.Connection, node_id: int) -> DialogueNode | None:
        row = conn.execute(
            f"""SELECT {NODE_COLUMNS}
                FROM dialogue_nodes WHERE id = ?""",
            (node_id,),
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def by_speaker(
        cls, conn: sqlite3.Connection, speaker: str, page_id: int | None = None
    ) -> list[DialogueNode]:
        if page_id is not None:
            rows = conn.execute(
                f"""SELECT {NODE_COLUMNS}
                    FROM dialogue_nodes WHERE speaker = ? AND page_id = ? ORDER BY sort_order""",
                (speaker, page_id),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""SELECT {NODE_COLUMNS}
                    FROM dialogue_nodes WHERE speaker = ? ORDER BY page_id, sort_order""",
                (speaker,),
            ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def search(
        cls, conn: sqlite3.Connection, text: str, page_id: int | None = None
    ) -> list[DialogueNode]:
        if page_id is not None:
            rows = conn.execute(
                f"""SELECT {NODE_COLUMNS}
                    FROM dialogue_nodes WHERE text LIKE ? AND page_id = ? ORDER BY sort_order""",
                (f"%{text}%", page_id),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""SELECT {NODE_COLUMNS}
                    FROM dialogue_nodes WHERE text LIKE ? ORDER BY page_id, sort_order""",
                (f"%{text}%",),
            ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def by_section(cls, conn: sqlite3.Connection, page_id: int, section: str) -> list[DialogueNode]:
        rows = conn.execute(
            f"""SELECT {NODE_COLUMNS}
                FROM dialogue_nodes WHERE page_id = ? AND section = ? ORDER BY sort_order""",
            (page_id, section),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    def children(self, conn: sqlite3.Connection) -> list[DialogueNode]:
        rows = conn.execute(
            f"""SELECT {NODE_COLUMNS}
                FROM dialogue_nodes WHERE parent_id = ? ORDER BY sort_order""",
            (self.id,),
        ).fetchall()
        return [self._from_row(r) for r in rows]

    def subtree(self, conn: sqlite3.Connection) -> list[DialogueNode]:
        """Return this node and all descendants via recursive CTE."""
        rows = conn.execute(
            f"""WITH RECURSIVE descendants AS (
                    SELECT {NODE_COLUMNS}
                    FROM dialogue_nodes WHERE id = ?
                    UNION ALL
                    SELECT dn.id, dn.page_id, dn.parent_id, dn.sort_order, dn.depth,
                           dn.node_type, dn.speaker, dn.text, dn.section, dn.continue_target_id
                    FROM dialogue_nodes dn
                    JOIN descendants d ON dn.parent_id = d.id
                )
                SELECT * FROM descendants ORDER BY sort_order""",
            (self.id,),
        ).fetchall()
        return [self._from_row(r) for r in rows]

    def parent(self, conn: sqlite3.Connection) -> DialogueNode | None:
        if self.parent_id is None:
            return None
        return self.by_id(conn, self.parent_id)

    def ancestors(self, conn: sqlite3.Connection) -> list[DialogueNode]:
        """Return the path from root to this node (excluding self)."""
        path: list[DialogueNode] = []
        current = self
        while current.parent_id is not None:
            current = self.by_id(conn, current.parent_id)
            if current is None:
                break
            path.append(current)
        path.reverse()
        return path

    def continue_target(self, conn: sqlite3.Connection) -> DialogueNode | None:
        """Resolve the ACTION/continue target of this node, if any."""
        if self.continue_target_id is None:
            return None
        return self.by_id(conn, self.continue_target_id)

    def tags(self, conn: sqlite3.Connection):
        from ragger.dialogue.dialogue_tag import DialogueTag

        return DialogueTag.by_node(conn, self.id)

    def requirement_groups(self, conn: sqlite3.Connection):
        from ragger.requirements import RequirementGroup

        return RequirementGroup.for_dialogue_node(conn, self.id)

    def page(self, conn: sqlite3.Connection):
        from ragger.dialogue.dialogue_page import DialoguePage

        row = conn.execute(
            f"SELECT {PAGE_COLUMNS} FROM dialogue_pages WHERE id = ?", (self.page_id,)
        ).fetchone()
        return DialoguePage._from_row(row) if row else None

    _NODE_TYPE_FORMAT = {
        DialogueNodeType.OPTION: "[{}]",
        DialogueNodeType.CONDITION: "({})",
        DialogueNodeType.ACTION: "-> {}",
        DialogueNodeType.SELECT: "? {}",
        DialogueNodeType.BOX: "* {}",
        DialogueNodeType.QUEST_ACTION: "~ {}",
    }

    def render(self) -> str:
        """Render this node as a single indented line with node ID prefix."""
        indent = "  " * (self.depth - 1)
        text = self.text or ""
        fmt = self._NODE_TYPE_FORMAT.get(self.node_type)
        if fmt:
            line = f"{indent}{fmt.format(text)}"
        else:
            speaker = f"{self.speaker}: " if self.speaker else ""
            line = f"{indent}{speaker}{text}"
        return f"{self.id:06d}: {line}"

    @classmethod
    def _from_row(cls, row: tuple) -> DialogueNode:
        return cls(
            id=row[0],
            page_id=row[1],
            parent_id=row[2],
            sort_order=row[3],
            depth=row[4],
            node_type=DialogueNodeType(row[5]),
            speaker=row[6],
            text=row[7],
            section=row[8],
            continue_target_id=row[9],
        )
