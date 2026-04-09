"""Fetch all OSRS currencies from the wiki Category:Currency.

Splits each currency page into one of two tables based on whether a
matching item exists:

- **physical_currencies** — currency that has an item form (Coins,
  Tokkul, Trading sticks, Platinum tokens, Mark of grace, etc.).
  Linked to items.id.
- **virtual_currencies** — reward counters with no item form (Slayer
  reward points, Carpenter points, Void Knight commendation points,
  etc.). varbit_id starts NULL and can be filled in later by the
  game-var classification pipeline.

Must run after fetch_items.py so the items table exists for linking.
"""

import argparse
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.wiki import (
    fetch_category_members,
    record_attributions_batch,
)


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    pages = fetch_category_members(
        "Currency",
        exclude_titles={"Currency", "Currencies"},
    )
    print(f"Found {len(pages)} pages in Category:Currency")

    conn = get_connection(db_path)

    item_lookup: dict[str, int] = {
        name: id for id, name in conn.execute("SELECT id, name FROM items").fetchall()
    }

    physical = 0
    virtual = 0
    for page_name in pages:
        item_id = item_lookup.get(page_name)
        if item_id is not None:
            conn.execute(
                "INSERT OR IGNORE INTO physical_currencies (name, item_id) VALUES (?, ?)",
                (page_name, item_id),
            )
            physical += 1
        else:
            conn.execute(
                "INSERT OR IGNORE INTO virtual_currencies (name, varbit_id) VALUES (?, NULL)",
                (page_name,),
            )
            virtual += 1

    conn.commit()
    print(f"Inserted {physical} physical currencies, {virtual} virtual currencies")

    print("\n=== Physical ===")
    for (name,) in conn.execute("SELECT name FROM physical_currencies ORDER BY name"):
        print(f"  {name}")

    print("\n=== Virtual ===")
    for (name,) in conn.execute("SELECT name FROM virtual_currencies ORDER BY name"):
        print(f"  {name}")

    record_attributions_batch(conn, "currencies", pages)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch OSRS currencies into the database")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
