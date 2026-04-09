"""Refine dialogue_nodes.text to use typed entity prefixes on wiki links.

Walks every dialogue node, looks up each ``[display](wiki:Page_Slug)``
markdown link against the entity tables, and rewrites the prefix to
the matching entity type (``npc:``, ``item:``, ``quest:`` etc.).
Anything not found in any entity table stays as ``wiki:``.

Idempotent and re-runnable. Must run after ``fetch_dialogues.py`` and
after all entity-table fetchers, but before
``compute_dialogue_instructions.py`` so the IR inherits the refined
text from ``dialogue_nodes``.
"""

import argparse
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.dialogue.dialogue_entity_links import (
    build_entity_lookup,
    refine_entity_links,
)


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    lookup = build_entity_lookup(conn)
    print(f"Built lookup with {len(lookup)} entity names", flush=True)

    rows = conn.execute(
        "SELECT id, text FROM dialogue_nodes WHERE text LIKE '%](wiki:%'"
    ).fetchall()
    print(f"Refining {len(rows)} candidate rows...", flush=True)

    updates: list[tuple[str, int]] = []
    refined_count = 0
    for node_id, text in rows:
        new_text = refine_entity_links(text, lookup)
        if new_text != text:
            updates.append((new_text, node_id))
            refined_count += 1

    if updates:
        conn.executemany(
            "UPDATE dialogue_nodes SET text = ? WHERE id = ?",
            updates,
        )
        conn.commit()

    print(f"Refined {refined_count} dialogue nodes", flush=True)

    print("\nLink type distribution after refinement:", flush=True)
    for entity_type in (
        "wiki", "npc", "item", "quest", "monster",
        "location", "shop", "activity", "equipment",
    ):
        count = conn.execute(
            f"SELECT COUNT(*) FROM dialogue_nodes WHERE text LIKE '%]({entity_type}:%'"
        ).fetchone()[0]
        if count:
            print(f"  {entity_type:10s} {count}", flush=True)

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Refine dialogue entity link prefixes")
    parser.add_argument("--db", type=Path, default=Path("data/ragger.db"))
    args = parser.parse_args()
    ingest(args.db)
