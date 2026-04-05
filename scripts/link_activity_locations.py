"""Link activities to locations by matching activity location text to location names.

Updates the location_id foreign key on the activities table.
Requires: fetch_activities.py and fetch_locations.py to have been run first.
"""

import argparse
from pathlib import Path

from ragger.db import create_tables, get_connection


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    location_ids = dict(conn.execute("SELECT name, id FROM locations").fetchall())
    activities = conn.execute("SELECT id, name, location FROM activities").fetchall()

    matched = 0
    unmatched = 0

    for activity_id, activity_name, activity_location in activities:
        if not activity_location:
            unmatched += 1
            continue

        loc_id = location_ids.get(activity_location)

        # Try first part of comma-separated (e.g. "Barbarian Outpost, south of Baxtorian Falls")
        if loc_id is None and "," in activity_location:
            first_part = activity_location.split(",")[0].strip()
            loc_id = location_ids.get(first_part)

        if loc_id is not None:
            conn.execute("UPDATE activities SET location_id = ? WHERE id = ?", (loc_id, activity_id))
            matched += 1
        else:
            print(f"  Warning: no location match for activity '{activity_name}' (location: '{activity_location}')")
            unmatched += 1

    conn.commit()
    print(f"Linked {matched} activities to locations ({unmatched} unmatched) in {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Link activities to locations")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
