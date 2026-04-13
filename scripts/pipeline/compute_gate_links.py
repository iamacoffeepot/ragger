"""Insert gate/door objects as one-tile walking links in `map_links`.

Gates in OSRS are walls with a click action (`Open`, `Pay-toll`, etc.)
that don't show up as passable in the collision grid. Most are cosmetic
— you can walk around them and the two sides are already in the same
blob — but some actually partition space (e.g. the Taverley <-> Falador
gate). For those we emit a `GATE` map_link so the pathfinder can route
through the wall as an explicit "open the gate" step.

Requires `compute_blobs.py` to have populated the BLOB map squares.
"""

import argparse
import json
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.enums import MapLinkType
from ragger.map import blob_at

PASSABLE_OPS = {
    "Climb-over", "Climb-through", "Squeeze-through", "Pay-toll",
    "Go-through", "Push", "Crawl-through", "Jump-over", "Jump-across",
    "Vault",
}
NAME_HINTS = ("door", "gate", "archway", "stile", "doorway")
NAME_EXCL = ("trapdoor", "hotspot", "cellar")

# Orientation -> (this_tile_offset, other_tile_offset) for loc-type 0 (flat
# wall on one edge). Orient 0=W, 1=N, 2=E, 3=S in Jagex convention.
ORIENT_NEIGHBORS: dict[int, tuple[int, int]] = {
    0: (-1, 0),  # W edge -> link (x-1, y) <-> (x, y)
    1: (0, +1),  # N edge -> link (x, y) <-> (x, y+1)
    2: (+1, 0),  # E edge
    3: (0, -1),  # S edge
}


def is_gate(defn: dict) -> bool:
    name = (defn.get("name") or "").lower()
    if any(h in name for h in NAME_EXCL):
        return False
    ops = [o["text"] for o in (defn.get("ops") or []) if o and o.get("text")]
    name_match = any(h in name for h in NAME_HINTS)
    if name_match and "Open" in ops:
        return True
    return any(o in PASSABLE_OPS for o in ops)


def ingest(db_path: Path, definitions_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    with open(definitions_path) as f:
        defs = {d["id"]: d for d in json.load(f)}

    gate_ids = {gid for gid, d in defs.items() if is_gate(d)}
    print(f"Gate-eligible object defs: {len(gate_ids)}")

    rows = conn.execute(
        "SELECT game_id, x, y, plane, type, orientation FROM object_locations "
        "WHERE plane = 0 AND game_id IN ({})".format(
            ",".join("?" * len(gate_ids))
        ),
        list(gate_ids),
    ).fetchall()
    print(f"Placed gate instances: {len(rows)}")

    locations = conn.execute(
        "SELECT id, name, x, y FROM locations WHERE x IS NOT NULL AND y IS NOT NULL",
    ).fetchall()

    def nearest_name(x: int, y: int) -> str:
        best_name = ""
        best_d = float("inf")
        for _, name, lx, ly in locations:
            d = max(abs(x - lx), abs(y - ly))
            if d < best_d:
                best_d = d
                best_name = name
        return best_name

    # Wipe any prior GATE links so re-runs are idempotent
    conn.execute("DELETE FROM map_links WHERE type = ?", (MapLinkType.GATE.value,))

    inserted = 0
    skipped_same_blob = 0
    skipped_unwalkable = 0
    skipped_no_orient = 0
    for game_id, x, y, plane, ltype, orient in rows:
        if ltype != 0:
            # Only flat walls have a well-defined perpendicular tile pair.
            # Other loc-types (corners, freestanding) need per-type geometry
            # we haven't written yet.
            skipped_no_orient += 1
            continue
        offs = ORIENT_NEIGHBORS.get(orient)
        if offs is None:
            skipped_no_orient += 1
            continue

        ax, ay = x, y
        bx, by = x + offs[0], y + offs[1]

        blob_a = blob_at(conn, ax, ay, plane)
        blob_b = blob_at(conn, bx, by, plane)
        if blob_a == 0 or blob_b == 0:
            skipped_unwalkable += 1
            continue
        if blob_a == blob_b:
            skipped_same_blob += 1
            continue

        name = defs[game_id].get("name", "Gate")
        src_loc = nearest_name(ax, ay)
        dst_loc = nearest_name(bx, by)
        description = f"{name} ({game_id})"

        # Bidirectional: both sides can walk through
        for (sx, sy, sloc, dx, dy, dloc) in (
            (ax, ay, src_loc, bx, by, dst_loc),
            (bx, by, dst_loc, ax, ay, src_loc),
        ):
            conn.execute(
                "INSERT INTO map_links "
                "(src_location, dst_location, src_x, src_y, dst_x, dst_y, "
                "src_blob_id, dst_blob_id, type, description) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (sloc, dloc, sx, sy, dx, dy,
                 blob_a if (sx, sy) == (ax, ay) else blob_b,
                 blob_b if (sx, sy) == (ax, ay) else blob_a,
                 MapLinkType.GATE.value, description),
            )
            inserted += 1

    conn.commit()
    print(f"Inserted {inserted} gate map_links "
          f"(same-blob skipped: {skipped_same_blob}, "
          f"unwalkable skipped: {skipped_unwalkable}, "
          f"non-flat-wall skipped: {skipped_no_orient})")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Insert passable gate/door objects as GATE map_links",
    )
    parser.add_argument("--db", type=Path, default=Path("data/ragger.db"))
    parser.add_argument(
        "--definitions",
        type=Path,
        default=Path("data/cache-dump/object-definitions.json"),
    )
    args = parser.parse_args()
    ingest(args.db, args.definitions)
