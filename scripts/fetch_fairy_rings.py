"""Fetch fairy ring data and create map links between all fairy ring locations.

Every fairy ring connects to every other fairy ring, so this creates
bidirectional links between all pairs.

Stores fairy ring codes in map_links description field.
"""

import argparse
import re
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.enums import MapLinkType
from ragger.wiki import (
    extract_coords,
    fetch_page_wikitext_with_attribution,
    resolve_region,
    strip_wiki_links,
)

FAIRYCODE_PATTERN = re.compile(r"\{\{Fairycode\|(\w+)\}\}")


def parse_fairy_rings(wikitext: str) -> list[dict]:
    """Parse fairy ring entries from the Combinations tables."""
    rings: list[dict] = []
    rows = wikitext.split("|-")

    for row in rows:
        code_match = FAIRYCODE_PATTERN.search(row)
        if not code_match:
            continue
        code = code_match.group(1).upper()

        coords = extract_coords(row)
        if not coords:
            continue
        x, y = coords[0]

        # Extract location text from the cell after the Map template
        cells = row.split("\n|")
        location = ""
        for cell in cells:
            cell = cell.strip()
            if cell and "Fairycode" not in cell and "Map" not in cell and "id=" not in cell:
                location = strip_wiki_links(cell).strip()
                break

        region = resolve_region(strip_wiki_links(cells[3].strip()) if len(cells) > 3 else "")

        rings.append({
            "code": code,
            "x": x,
            "y": y,
            "location": location,
            "region": region,
        })

    return rings


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    print("Fetching fairy ring data...")
    wikitext = fetch_page_wikitext_with_attribution(conn, "Fairy rings", "map_links")
    rings = parse_fairy_rings(wikitext)
    print(f"Found {len(rings)} fairy ring codes")

    # Create bidirectional links between all pairs
    link_count = 0
    for i, from_ring in enumerate(rings):
        for j, to_ring in enumerate(rings):
            if i == j:
                continue
            conn.execute(
                """INSERT INTO map_links
                   (src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    from_ring["location"],
                    to_ring["location"],
                    from_ring["x"],
                    from_ring["y"],
                    to_ring["x"],
                    to_ring["y"],
                    MapLinkType.FAIRY_RING.value,
                    f"Fairy ring {from_ring['code']} -> {to_ring['code']}",
                ),
            )
            link_count += 1

    conn.commit()
    print(f"Inserted {link_count} fairy ring links into {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch fairy ring map links")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
