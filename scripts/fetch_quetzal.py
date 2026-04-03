"""Fetch Quetzal Transport System data and create map links between all stops.

Every quetzal stop connects to every other stop. Some stops must be
built before use (marked as "Unbuilt" on the wiki).
"""

import argparse
import re
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.enums import MapLinkType
from ragger.wiki import extract_coords, fetch_page_wikitext_with_attribution, strip_wiki_links


def parse_quetzal_stops(wikitext: str) -> list[dict]:
    """Parse quetzal transport stops from the Locations table."""
    stops: list[dict] = []
    rows = wikitext.split("|-")

    for row in rows:
        # Look for rows with Map templates
        coords = extract_coords(row)
        if not coords:
            continue

        # Extract location name from wiki link
        name_match = re.search(r"\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]", row)
        if not name_match:
            continue
        name = name_match.group(1).strip()

        x, y = coords[0]

        built = "Unbuilt" not in row

        stops.append({
            "name": name,
            "x": x,
            "y": y,
            "built": built,
        })

    return stops


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    print("Fetching Quetzal Transport System data...")
    wikitext = fetch_page_wikitext_with_attribution(conn, "Quetzal Transport System", "map_links")
    stops = parse_quetzal_stops(wikitext)
    print(f"Found {len(stops)} quetzal stops ({sum(1 for s in stops if s['built'])} built, {sum(1 for s in stops if not s['built'])} unbuilt)")

    link_count = 0
    for i, from_stop in enumerate(stops):
        for j, to_stop in enumerate(stops):
            if i == j:
                continue
            built_note = "" if from_stop["built"] and to_stop["built"] else " (requires building)"
            conn.execute(
                """INSERT INTO map_links
                   (src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    from_stop["name"],
                    to_stop["name"],
                    from_stop["x"],
                    from_stop["y"],
                    to_stop["x"],
                    to_stop["y"],
                    MapLinkType.QUETZAL.value,
                    f"Quetzal: {from_stop['name']} -> {to_stop['name']}{built_note}",
                ),
            )
            link_count += 1

    conn.commit()
    print(f"Inserted {link_count} quetzal transport links into {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Quetzal Transport System map links")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
