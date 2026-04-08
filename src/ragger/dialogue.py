from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ragger.enums import DialogueEdgeType, DialogueNodeType


@dataclass
class DialoguePage:
    id: int
    title: str
    page_type: str | None

    @classmethod
    def all(cls, conn: sqlite3.Connection, page_type: str | None = None) -> list[DialoguePage]:
        query = "SELECT id, title, page_type FROM dialogue_pages"
        params: list = []
        if page_type is not None:
            query += " WHERE page_type = ?"
            params.append(page_type)
        query += " ORDER BY title"
        return [cls(*r) for r in conn.execute(query, params).fetchall()]

    @classmethod
    def by_title(cls, conn: sqlite3.Connection, title: str) -> DialoguePage | None:
        row = conn.execute(
            "SELECT id, title, page_type FROM dialogue_pages WHERE title = ?", (title,)
        ).fetchone()
        return cls(*row) if row else None

    @classmethod
    def search(cls, conn: sqlite3.Connection, title: str) -> list[DialoguePage]:
        rows = conn.execute(
            "SELECT id, title, page_type FROM dialogue_pages WHERE title LIKE ? ORDER BY title",
            (f"%{title}%",),
        ).fetchall()
        return [cls(*r) for r in rows]

    def nodes(self, conn: sqlite3.Connection) -> list[DialogueNode]:
        return DialogueNode.by_page(conn, self.id)

    def roots(self, conn: sqlite3.Connection) -> list[DialogueNode]:
        """Return only the top-level nodes (no parent)."""
        rows = conn.execute(
            """SELECT id, page_id, parent_id, sort_order, depth, node_type, speaker, text, section
               FROM dialogue_nodes WHERE page_id = ? AND parent_id IS NULL
               ORDER BY sort_order""",
            (self.id,),
        ).fetchall()
        return [DialogueNode._from_row(r) for r in rows]

    def render(self, conn: sqlite3.Connection, section: str | None = None) -> str:
        """Render the dialogue tree as indented text.

        Each line is prefixed with a zero-padded node ID and a colon.
        If section is given, only nodes in that section are included
        and the section header is omitted.  Resolved ``continues`` edges
        are rendered as ``-> #<target_id>``.
        """
        if section is not None:
            nodes = DialogueNode.by_section(conn, self.id, section)
        else:
            nodes = self.nodes(conn)

        # Build continues edge lookup
        continues: dict[int, int] = {}
        rows = conn.execute(
            """SELECT de.from_node_id, de.to_node_id
               FROM dialogue_edges de
               JOIN dialogue_nodes dn ON dn.id = de.from_node_id
               WHERE dn.page_id = ? AND de.edge_type = ?""",
            (self.id, DialogueEdgeType.CONTINUES.value),
        ).fetchall()
        for from_id, to_id in rows:
            continues[from_id] = to_id

        lines: list[str] = []
        current_section: str | None = None

        for node in nodes:
            if section is None and node.section != current_section:
                current_section = node.section
                if current_section:
                    if lines:
                        lines.append("")
                    lines.append(f"== {current_section} ==")

            if node.id in continues:
                indent = "  " * (node.depth - 1)
                lines.append(f"{node.id:06d}: {indent}-> #{continues[node.id]:06d}")
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

    @classmethod
    def by_page(cls, conn: sqlite3.Connection, page_id: int) -> list[DialogueNode]:
        rows = conn.execute(
            """SELECT id, page_id, parent_id, sort_order, depth, node_type, speaker, text, section
               FROM dialogue_nodes WHERE page_id = ? ORDER BY sort_order""",
            (page_id,),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def by_id(cls, conn: sqlite3.Connection, node_id: int) -> DialogueNode | None:
        row = conn.execute(
            """SELECT id, page_id, parent_id, sort_order, depth, node_type, speaker, text, section
               FROM dialogue_nodes WHERE id = ?""",
            (node_id,),
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def by_speaker(cls, conn: sqlite3.Connection, speaker: str, page_id: int | None = None) -> list[DialogueNode]:
        if page_id is not None:
            rows = conn.execute(
                """SELECT id, page_id, parent_id, sort_order, depth, node_type, speaker, text, section
                   FROM dialogue_nodes WHERE speaker = ? AND page_id = ? ORDER BY sort_order""",
                (speaker, page_id),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, page_id, parent_id, sort_order, depth, node_type, speaker, text, section
                   FROM dialogue_nodes WHERE speaker = ? ORDER BY page_id, sort_order""",
                (speaker,),
            ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def search(cls, conn: sqlite3.Connection, text: str, page_id: int | None = None) -> list[DialogueNode]:
        if page_id is not None:
            rows = conn.execute(
                """SELECT id, page_id, parent_id, sort_order, depth, node_type, speaker, text, section
                   FROM dialogue_nodes WHERE text LIKE ? AND page_id = ? ORDER BY sort_order""",
                (f"%{text}%", page_id),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, page_id, parent_id, sort_order, depth, node_type, speaker, text, section
                   FROM dialogue_nodes WHERE text LIKE ? ORDER BY page_id, sort_order""",
                (f"%{text}%",),
            ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def by_section(cls, conn: sqlite3.Connection, page_id: int, section: str) -> list[DialogueNode]:
        rows = conn.execute(
            """SELECT id, page_id, parent_id, sort_order, depth, node_type, speaker, text, section
               FROM dialogue_nodes WHERE page_id = ? AND section = ? ORDER BY sort_order""",
            (page_id, section),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    def children(self, conn: sqlite3.Connection) -> list[DialogueNode]:
        rows = conn.execute(
            """SELECT id, page_id, parent_id, sort_order, depth, node_type, speaker, text, section
               FROM dialogue_nodes WHERE parent_id = ? ORDER BY sort_order""",
            (self.id,),
        ).fetchall()
        return [self._from_row(r) for r in rows]

    def subtree(self, conn: sqlite3.Connection) -> list[DialogueNode]:
        """Return this node and all descendants via recursive CTE."""
        rows = conn.execute(
            """WITH RECURSIVE descendants AS (
                   SELECT id, page_id, parent_id, sort_order, depth, node_type, speaker, text, section
                   FROM dialogue_nodes WHERE id = ?
                   UNION ALL
                   SELECT dn.id, dn.page_id, dn.parent_id, dn.sort_order, dn.depth,
                          dn.node_type, dn.speaker, dn.text, dn.section
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

    def tags(self, conn: sqlite3.Connection) -> list[DialogueTag]:
        return DialogueTag.by_node(conn, self.id)

    def edges_out(self, conn: sqlite3.Connection, edge_type: DialogueEdgeType | None = None) -> list[DialogueEdge]:
        """Outgoing edges from this node."""
        return DialogueEdge.from_node(conn, self.id, edge_type)

    def edges_in(self, conn: sqlite3.Connection, edge_type: DialogueEdgeType | None = None) -> list[DialogueEdge]:
        """Incoming edges to this node."""
        return DialogueEdge.to_node(conn, self.id, edge_type)

    def requirement_groups(self, conn: sqlite3.Connection) -> list[RequirementGroup]:
        from ragger.requirements import RequirementGroup

        return RequirementGroup.for_dialogue_node(conn, self.id)

    def page(self, conn: sqlite3.Connection) -> DialoguePage | None:
        row = conn.execute(
            "SELECT id, title, page_type FROM dialogue_pages WHERE id = ?", (self.page_id,)
        ).fetchone()
        return DialoguePage(*row) if row else None

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
        )


@dataclass
class DialogueTag:
    id: int
    node_id: int
    entity_type: str
    entity_name: str
    entity_id: int | None

    @classmethod
    def by_node(cls, conn: sqlite3.Connection, node_id: int) -> list[DialogueTag]:
        rows = conn.execute(
            "SELECT id, node_id, entity_type, entity_name, entity_id FROM dialogue_tags WHERE node_id = ?",
            (node_id,),
        ).fetchall()
        return [cls(*r) for r in rows]

    @classmethod
    def by_entity(cls, conn: sqlite3.Connection, entity_type: str, entity_name: str) -> list[DialogueTag]:
        rows = conn.execute(
            """SELECT id, node_id, entity_type, entity_name, entity_id
               FROM dialogue_tags WHERE entity_type = ? AND entity_name = ?""",
            (entity_type, entity_name),
        ).fetchall()
        return [cls(*r) for r in rows]

    @classmethod
    def by_entity_type(cls, conn: sqlite3.Connection, entity_type: str) -> list[DialogueTag]:
        rows = conn.execute(
            "SELECT id, node_id, entity_type, entity_name, entity_id FROM dialogue_tags WHERE entity_type = ?",
            (entity_type,),
        ).fetchall()
        return [cls(*r) for r in rows]

    @classmethod
    def search(cls, conn: sqlite3.Connection, entity_name: str) -> list[DialogueTag]:
        rows = conn.execute(
            """SELECT id, node_id, entity_type, entity_name, entity_id
               FROM dialogue_tags WHERE entity_name LIKE ?""",
            (f"%{entity_name}%",),
        ).fetchall()
        return [cls(*r) for r in rows]

    def node(self, conn: sqlite3.Connection) -> DialogueNode | None:
        return DialogueNode.by_id(conn, self.node_id)


@dataclass
class DialogueEdge:
    id: int
    from_node_id: int
    to_node_id: int
    edge_type: DialogueEdgeType

    @classmethod
    def _from_row(cls, row: tuple) -> DialogueEdge:
        return cls(row[0], row[1], row[2], DialogueEdgeType(row[3]))

    @classmethod
    def from_node(cls, conn: sqlite3.Connection, node_id: int,
                  edge_type: DialogueEdgeType | None = None) -> list[DialogueEdge]:
        """Outgoing edges from a node, optionally filtered by type."""
        if edge_type is not None:
            rows = conn.execute(
                """SELECT id, from_node_id, to_node_id, edge_type
                   FROM dialogue_edges WHERE from_node_id = ? AND edge_type = ?
                   ORDER BY id""",
                (node_id, edge_type.value),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, from_node_id, to_node_id, edge_type
                   FROM dialogue_edges WHERE from_node_id = ? ORDER BY id""",
                (node_id,),
            ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def to_node(cls, conn: sqlite3.Connection, node_id: int,
                edge_type: DialogueEdgeType | None = None) -> list[DialogueEdge]:
        """Incoming edges to a node, optionally filtered by type."""
        if edge_type is not None:
            rows = conn.execute(
                """SELECT id, from_node_id, to_node_id, edge_type
                   FROM dialogue_edges WHERE to_node_id = ? AND edge_type = ?
                   ORDER BY id""",
                (node_id, edge_type.value),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, from_node_id, to_node_id, edge_type
                   FROM dialogue_edges WHERE to_node_id = ? ORDER BY id""",
                (node_id,),
            ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def by_page(cls, conn: sqlite3.Connection, page_id: int,
                edge_type: DialogueEdgeType | None = None) -> list[DialogueEdge]:
        """All edges for nodes on a page, optionally filtered by type."""
        if edge_type is not None:
            rows = conn.execute(
                """SELECT de.id, de.from_node_id, de.to_node_id, de.edge_type
                   FROM dialogue_edges de
                   JOIN dialogue_nodes dn ON dn.id = de.from_node_id
                   WHERE dn.page_id = ? AND de.edge_type = ?
                   ORDER BY de.id""",
                (page_id, edge_type.value),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT de.id, de.from_node_id, de.to_node_id, de.edge_type
                   FROM dialogue_edges de
                   JOIN dialogue_nodes dn ON dn.id = de.from_node_id
                   WHERE dn.page_id = ?
                   ORDER BY de.id""",
                (page_id,),
            ).fetchall()
        return [cls._from_row(r) for r in rows]

    def source(self, conn: sqlite3.Connection) -> DialogueNode | None:
        return DialogueNode.by_id(conn, self.from_node_id)

    def target(self, conn: sqlite3.Connection) -> DialogueNode | None:
        return DialogueNode.by_id(conn, self.to_node_id)
