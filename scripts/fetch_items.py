"""Fetch all OSRS items from the wiki API and insert into the items table."""

import argparse
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.wiki import fetch_category_members, record_attribution


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    items = fetch_category_members(
        "Items",
        exclude_prefixes=("Items/",),
        exclude_titles={"Items"},
        exclude_namespaces={2},
    )

    conn = get_connection(db_path)
    conn.executemany(
        "INSERT OR IGNORE INTO items (name) VALUES (?)",
        [(item,) for item in items],
    )
    record_attribution(conn, "items", "Category:Items", ["Category contributors"])
    conn.commit()
    print(f"Inserted {conn.total_changes} items into {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch OSRS items into the database")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
