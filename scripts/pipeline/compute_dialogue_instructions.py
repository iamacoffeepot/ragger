"""Compute the flattened instruction stream for every dialogue page.

Reads dialogue_pages + dialogue_nodes, runs flatten then the canonical
pass pipeline, and writes the result to dialogue_instructions. Idempotent
— existing rows for a page are deleted before rewriting.
"""

import argparse
import sys
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.dialogue.dialogue_flatten import flatten
from ragger.dialogue.dialogue_instruction import Instruction
from ragger.dialogue.dialogue_page import DialoguePage
from ragger.dialogue.dialogue_passes import PASSES, UnreachableContentError


def ingest(db_path: Path) -> int:
    create_tables(db_path)
    conn = get_connection(db_path)

    conn.execute("DELETE FROM dialogue_instructions")

    pages = DialoguePage.all(conn)
    print(f"Computing instructions for {len(pages)} dialogue pages...", flush=True)

    total_instr = 0
    errors: list[tuple[DialoguePage, UnreachableContentError]] = []
    for page in pages:
        try:
            instructions = flatten(conn, page)
            for p in PASSES:
                instructions = p(instructions)
        except UnreachableContentError as exc:
            errors.append((page, exc))
            continue
        Instruction.save_all_for_page(conn, page.id, instructions)
        total_instr += len(instructions)

    conn.commit()

    print(f"Wrote {total_instr} instructions", flush=True)

    print("\nOp counts:", flush=True)
    for row in conn.execute(
        "SELECT op, COUNT(*) FROM dialogue_instructions GROUP BY op ORDER BY 2 DESC"
    ):
        print(f"  {row[0]:10s} {row[1]}", flush=True)

    if errors:
        print(f"\n{len(errors)} pages had unreachable content (skipped):", flush=True)
        for page, exc in errors:
            print(f"  [{page.id}] {page.title}: {exc}", flush=True)

    conn.close()
    return 1 if errors else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute dialogue instruction streams")
    parser.add_argument("--db", type=Path, default=Path("data/ragger.db"))
    args = parser.parse_args()
    sys.exit(ingest(args.db))
