"""Import interactive object spawn locations from JSON produced by DumpObjectLocations into the database."""

import argparse
import json
from pathlib import Path

from ragger.db import create_tables, get_connection

DEFAULT_INPUT = Path(__file__).parents[2] / "data/cache-dump/object-locations.json"


def ingest(db_path: Path, input_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    conn.execute("DELETE FROM object_locations")

    data = json.loads(input_path.read_text())

    conn.executemany(
        "INSERT INTO object_locations (game_id, x, y, plane, type, orientation) VALUES (?, ?, ?, ?, ?, ?)",
        data,
    )

    conn.commit()
    print(f"Imported {len(data)} object locations")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import object spawn locations into the database")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Path to object-locations.json from DumpObjectLocations",
    )
    args = parser.parse_args()
    ingest(args.db, args.input)
