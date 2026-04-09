"""Instruction: one line in a page's flattened instruction stream."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from ragger.dialogue.dialogue_helpers import INSTR_COLUMNS
from ragger.enums import InstructionOp


@dataclass
class Instruction:
    """One line in a page's flattened instruction stream.

    Addresses (``addr``) are global within a page. Sections are a column,
    not a partition — cross-section references are just regular local
    addresses. The pipeline never introduces external targets.
    """

    page_id: int
    addr: int
    section: str
    op: InstructionOp
    text: str = ""
    speaker: str | None = None
    fallthrough: bool = True
    targets: list[int] = field(default_factory=list)
    target_labels: list[str] = field(default_factory=list)
    target_predicates: list[str] = field(default_factory=list)
    dead: bool = False

    def __str__(self) -> str:
        speaker = f" {self.speaker}" if self.speaker else ""
        if self.op in (InstructionOp.MENU, InstructionOp.SWITCH) and self.target_labels:
            preds = self.target_predicates or []
            parts = []
            for i, (lbl, t) in enumerate(zip(self.target_labels, self.targets)):
                pred = preds[i] if i < len(preds) else ""
                if pred:
                    parts.append(f'"{lbl}" if ({pred}) -> @{t:04d}')
                else:
                    parts.append(f'"{lbl}" -> @{t:04d}')
            targets_str = f" [{', '.join(parts)}]"
        elif self.targets:
            targets_str = f" -> {', '.join(f'@{t:04d}' for t in self.targets)}"
        elif self.op == InstructionOp.GOTO:
            targets_str = " -> ?"
        else:
            targets_str = ""
        fall = "" if self.fallthrough else " [terminal]"
        text = f' "{self.text}"' if self.text else ""
        return f"{self.addr:04d}: {self.op}{speaker}{text}{targets_str}{fall}"

    @classmethod
    def for_page(cls, conn: sqlite3.Connection, page_id: int) -> list[Instruction]:
        rows = conn.execute(
            f"""SELECT {INSTR_COLUMNS}
                FROM dialogue_instructions WHERE page_id = ? ORDER BY addr""",
            (page_id,),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def by_section(
        cls, conn: sqlite3.Connection, page_id: int, section: str
    ) -> list[Instruction]:
        rows = conn.execute(
            f"""SELECT {INSTR_COLUMNS}
                FROM dialogue_instructions WHERE page_id = ? AND section = ? ORDER BY addr""",
            (page_id, section),
        ).fetchall()
        return [cls._from_row(r) for r in rows]

    @classmethod
    def delete_for_page(cls, conn: sqlite3.Connection, page_id: int) -> None:
        conn.execute("DELETE FROM dialogue_instructions WHERE page_id = ?", (page_id,))

    @classmethod
    def save_all_for_page(
        cls, conn: sqlite3.Connection, page_id: int, instructions: list[Instruction]
    ) -> None:
        cls.delete_for_page(conn, page_id)
        rows = [
            (
                page_id,
                i.addr,
                i.section,
                i.op,
                i.text,
                i.speaker,
                int(i.fallthrough),
                json.dumps(i.targets),
                json.dumps(i.target_labels),
                json.dumps(i.target_predicates),
            )
            for i in instructions
        ]
        conn.executemany(
            f"""INSERT INTO dialogue_instructions ({INSTR_COLUMNS})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )

    @classmethod
    def _from_row(cls, row: tuple) -> Instruction:
        return cls(
            page_id=row[0],
            addr=row[1],
            section=row[2],
            op=InstructionOp(row[3]),
            text=row[4],
            speaker=row[5],
            fallthrough=bool(row[6]),
            targets=json.loads(row[7]),
            target_labels=json.loads(row[8]),
            target_predicates=json.loads(row[9]),
        )
