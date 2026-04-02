"""Derive facility bitmasks on locations from the facilities table.

For each facility, finds the nearest location by Chebyshev distance
and sets the corresponding bit on that location's facilities column.

Requires: fetch_facilities.py and fetch_locations.py to have been run first.
"""

import argparse
from pathlib import Path

from clogger.db import create_tables, get_connection
from clogger.enums import Facility
from clogger.location import Location


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    # Reset facilities bitmask
    conn.execute("UPDATE locations SET facilities = 0")

    facility_rows = conn.execute("SELECT id, type, x, y FROM facilities").fetchall()
    print(f"Loaded {len(facility_rows)} facilities")

    linked = 0
    for _, ftype, fx, fy in facility_rows:
        loc = Location.nearest(conn, fx, fy)
        if loc is not None:
            mask = Facility(ftype).mask
            conn.execute(
                "UPDATE locations SET facilities = facilities | ? WHERE id = ?",
                (mask, loc.id),
            )
            linked += 1

    conn.commit()

    # Report summary per facility type
    for facility in Facility:
        count = conn.execute(
            "SELECT COUNT(*) FROM locations WHERE facilities & ? != 0",
            (facility.mask,),
        ).fetchone()[0]
        print(f"  {facility.label}: {count} locations")

    print(f"\nLinked {linked} facilities to locations in {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Derive facility bitmasks on locations")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/clogger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
