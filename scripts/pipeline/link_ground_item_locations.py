"""Link ground items to items and locations.

Resolves item_name to item_id with normalization fallbacks (case-insensitive,
space before parens, dose suffix stripping).

Resolves location_id by finding the nearest location by Chebyshev distance.

Requires: fetch_items.py, fetch_locations.py, and fetch_ground_items.py.
"""

import argparse
import re
from pathlib import Path

from ragger.db import create_tables, get_connection

_DOSE_SUFFIX = re.compile(r"\s*\(\d+\)$")


def _build_item_lookup(conn) -> tuple[dict[str, int], dict[str, int]]:
    """Build exact and case-insensitive item name lookups."""
    item_rows = conn.execute("SELECT id, name FROM items").fetchall()
    exact: dict[str, int] = {name: id for id, name in item_rows}
    lower: dict[str, int] = {name.lower(): id for id, name in item_rows}
    return exact, lower


def _resolve_item(name: str, exact: dict[str, int], lower: dict[str, int]) -> int | None:
    """Try to match an item name with normalization fallbacks.

    1. Exact match
    2. Case-insensitive match
    3. Add space before parenthesized suffix: "Foo(bar)" -> "Foo (bar)"
    4. Strip dose/quantity suffix: "Foo (1)" -> "Foo"
    """
    if name in exact:
        return exact[name]

    if name.lower() in lower:
        return lower[name.lower()]

    spaced = re.sub(r"(\w)\(", r"\1 (", name)
    if spaced != name and spaced.lower() in lower:
        return lower[spaced.lower()]

    base = _DOSE_SUFFIX.sub("", spaced)
    if base != spaced and base.lower() in lower:
        return lower[base.lower()]

    return None


def _find_nearest_location(
    x: int, y: int, locations: list[tuple[int, int, int]],
) -> tuple[int, int]:
    """Find the nearest location by Chebyshev distance. Returns (id, distance)."""
    best_id = -1
    best_dist = float("inf")
    for loc_id, lx, ly in locations:
        dist = max(abs(x - lx), abs(y - ly))
        if dist < best_dist:
            best_dist = dist
            best_id = loc_id
    return best_id, int(best_dist)


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    # Item linking
    exact, lower = _build_item_lookup(conn)
    rows = conn.execute("SELECT id, item_name FROM ground_items WHERE item_id IS NULL").fetchall()

    item_matched = 0
    unmatched_items: set[str] = set()
    for row_id, item_name in rows:
        item_id = _resolve_item(item_name, exact, lower)
        if item_id is not None:
            conn.execute("UPDATE ground_items SET item_id = ? WHERE id = ?", (item_id, row_id))
            item_matched += 1
        else:
            unmatched_items.add(item_name)

    if unmatched_items:
        print(f"  {len(unmatched_items)} unrecognized items: {sorted(unmatched_items)[:10]}...")
    print(f"Linked {item_matched}/{len(rows)} ground items to items")

    # Location linking by nearest coordinates
    locations = conn.execute(
        "SELECT id, x, y FROM locations WHERE x IS NOT NULL AND y IS NOT NULL",
    ).fetchall()

    rows = conn.execute(
        "SELECT id, x, y FROM ground_items WHERE location_id IS NULL",
    ).fetchall()

    loc_matched = 0
    for row_id, x, y in rows:
        loc_id, dist = _find_nearest_location(x, y, locations)
        if loc_id >= 0:
            conn.execute(
                "UPDATE ground_items SET location_id = ? WHERE id = ?",
                (loc_id, row_id),
            )
            loc_matched += 1

    print(f"Linked {loc_matched}/{len(rows)} ground items to nearest locations")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Link ground items to items and locations")
    parser.add_argument("--db", type=Path, default=Path("data/ragger.db"))
    args = parser.parse_args()
    ingest(args.db)
