"""Link activities to locations by matching activity location text or coordinates.

First tries exact name match, then comma-split match, then falls back to
nearest location by coordinates. Updates the location_id foreign key.
Requires: fetch_activities.py and fetch_locations.py to have been run first.
"""

import argparse
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.location import Location


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    location_ids = dict(conn.execute("SELECT name, id FROM locations").fetchall())
    activities = conn.execute("SELECT id, name, location, x, y FROM activities").fetchall()

    matched_name = 0
    matched_coords = 0
    unmatched = 0

    for activity_id, activity_name, activity_location, x, y in activities:
        loc_id = None

        # Try exact name match
        if activity_location:
            loc_id = location_ids.get(activity_location)

            # Try first part of comma-separated
            if loc_id is None and "," in activity_location:
                first_part = activity_location.split(",")[0].strip()
                loc_id = location_ids.get(first_part)

        if loc_id is not None:
            conn.execute("UPDATE activities SET location_id = ? WHERE id = ?", (loc_id, activity_id))
            matched_name += 1
            continue

        # Fall back to nearest location by coordinates
        if x is not None and y is not None:
            nearest = Location.nearest(conn, x, y)
            if nearest:
                conn.execute("UPDATE activities SET location_id = ? WHERE id = ?", (nearest.id, activity_id))
                matched_coords += 1
                continue

        if activity_location and activity_location not in ("N/A", "Various", "Global"):
            print(f"  Warning: no location match for activity '{activity_name}' (location: '{activity_location}')")
        unmatched += 1

    conn.commit()
    total_matched = matched_name + matched_coords
    print(f"Linked {total_matched} activities to locations ({matched_name} by name, {matched_coords} by coords, {unmatched} unmatched) in {db_path}")
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
