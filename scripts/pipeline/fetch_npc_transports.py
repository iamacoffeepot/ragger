"""Seed map_links for one-off NPC-operated transports (carts, ferries, etc.).

Most transports have dedicated pipelines (fairy rings, quetzal, charter
ships, gnome gliders, magic teleports). What's left are bespoke NPCs
that offer a "Travel" / "Pay-fare" option to ferry the player between
two fixed points — the Hajedy/Vigroy Karamja cart, the dwarven mine
carts, magic carpets, and so on.

Rather than scraping each NPC's infobox we keep a small seed table
here. Each entry produces a pair of directed NPC_TRANSPORT map_links,
and any listed quest requirement is attached via requirement groups so
consumers check reachability against the player's live quest state.
"""

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.enums import MapLinkType
from ragger.wiki import link_group_requirement


@dataclass(frozen=True)
class NpcTransport:
    """A bidirectional NPC-operated transport between two locations.

    The NPC names are looked up in `npc_locations` to resolve coordinates,
    so the seed table stays coordinate-free and picks up any wiki updates
    to NPC spawn points on the next pipeline run.
    """
    src_location: str
    dst_location: str
    src_npc: str
    dst_npc: str
    description: str
    required_quest: str | None = None


_TRANSPORTS: list[NpcTransport] = [
    NpcTransport(
        src_location="Brimhaven",
        dst_location="Shilo Village",
        src_npc="Hajedy",
        dst_npc="Vigroy",
        description="Karamja cart (Hajedy / Vigroy): 200 gp flat fare",
        required_quest="Shilo Village",
    ),
]


def _lookup_npc_coord(conn: sqlite3.Connection, name: str) -> tuple[int, int]:
    row = conn.execute(
        "SELECT x, y FROM npc_locations WHERE name = ? ORDER BY id LIMIT 1",
        (name,),
    ).fetchone()
    if row is None:
        raise ValueError(f"No npc_locations row for {name!r} — run fetch_npc_locations.py first")
    return row[0], row[1]


def _lookup_quest_id(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute("SELECT id FROM quests WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise ValueError(f"No quest row for {name!r} — run fetch_quests.py first")
    return row[0]


def _insert_link(
    conn: sqlite3.Connection,
    src_loc: str, dst_loc: str,
    src_xy: tuple[int, int], dst_xy: tuple[int, int],
    description: str,
    quest_id: int | None,
) -> None:
    conn.execute(
        """INSERT INTO map_links
           (src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (src_loc, dst_loc, src_xy[0], src_xy[1], dst_xy[0], dst_xy[1],
         MapLinkType.NPC_TRANSPORT.value, description),
    )
    map_link_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    if quest_id is not None:
        link_group_requirement(
            conn,
            "group_quest_requirements",
            {"required_quest_id": quest_id, "partial": 0},
            "map_link_requirement_groups",
            "map_link_id",
            map_link_id,
        )


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    # Clear previous seed output so reruns are idempotent.
    conn.execute(
        "DELETE FROM map_link_requirement_groups "
        "WHERE map_link_id IN (SELECT id FROM map_links WHERE type = ?)",
        (MapLinkType.NPC_TRANSPORT.value,),
    )
    conn.execute("DELETE FROM map_links WHERE type = ?", (MapLinkType.NPC_TRANSPORT.value,))

    count = 0
    for t in _TRANSPORTS:
        src_xy = _lookup_npc_coord(conn, t.src_npc)
        dst_xy = _lookup_npc_coord(conn, t.dst_npc)
        quest_id = _lookup_quest_id(conn, t.required_quest) if t.required_quest else None
        _insert_link(conn, t.src_location, t.dst_location, src_xy, dst_xy, t.description, quest_id)
        _insert_link(conn, t.dst_location, t.src_location, dst_xy, src_xy, t.description, quest_id)
        count += 2

    conn.commit()
    print(f"Inserted {count} NPC transport links into {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed NPC-operated transport map links")
    parser.add_argument("--db", type=Path, default=Path("data/ragger.db"))
    args = parser.parse_args()
    ingest(args.db)
