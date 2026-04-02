"""Link shops to locations by matching shop location text to location names.

Updates the location_id foreign key on the shops table.
Requires: fetch_shops.py and fetch_locations.py to have been run first.
"""

import argparse
from pathlib import Path

from clogger.db import create_tables, get_connection


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    location_ids = dict(conn.execute("SELECT name, id FROM locations").fetchall())
    shops = conn.execute("SELECT id, name, location FROM shops").fetchall()

    matched = 0
    unmatched = 0

    for shop_id, shop_name, shop_location in shops:
        if not shop_location:
            unmatched += 1
            continue

        loc_id = location_ids.get(shop_location)

        # Try first part of comma-separated (e.g. "Mistrock, South of Aldarin")
        if loc_id is None and "," in shop_location:
            first_part = shop_location.split(",")[0].strip()
            loc_id = location_ids.get(first_part)

        if loc_id is not None:
            conn.execute("UPDATE shops SET location_id = ? WHERE id = ?", (loc_id, shop_id))
            matched += 1
        else:
            print(f"  Warning: no location match for shop '{shop_name}' (location: '{shop_location}')")
            unmatched += 1

    conn.commit()
    print(f"Linked {matched} shops to locations ({unmatched} unmatched) in {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Link shops to locations")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/clogger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
