"""Fetch charter ship destinations and create map links between all ports.

Every charter port connects to every other charter port.
Dock coordinates come from the Trader Stan's Trading Post shop page.
"""

import argparse
import re
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.enums import MapLinkType
from ragger.wiki import extract_coords, fetch_page_wikitext_with_attribution


def parse_charter_ports(wikitext: str) -> list[dict]:
    """Parse charter ship ports from the Trader Stan's Trading Post shop page."""
    ports: list[dict] = []
    lines = wikitext.split("\n")

    # Build version -> location name mapping
    locations: dict[str, str] = {}
    for line in lines:
        match = re.match(r"\|location(\d+)\s*=\s*\[\[([^\]|]+)", line)
        if match:
            locations[match.group(1)] = match.group(2).strip()

    # Extract map coordinates per version
    for line in lines:
        map_match = re.match(r"\|map(\d+)\s*=", line)
        if not map_match:
            continue
        version = map_match.group(1)
        coords = extract_coords(line)
        if not coords:
            continue

        name = locations.get(version)
        if not name:
            continue

        x, y = coords[0]
        ports.append({
            "name": name,
            "x": x,
            "y": y,
        })

    return ports


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    print("Fetching charter ship data...")
    wikitext = fetch_page_wikitext_with_attribution(conn, "Trader Stan's Trading Post", "map_links")
    ports = parse_charter_ports(wikitext)
    print(f"Found {len(ports)} charter ports")

    link_count = 0
    for i, from_port in enumerate(ports):
        for j, to_port in enumerate(ports):
            if i == j:
                continue
            conn.execute(
                """INSERT INTO map_links
                   (src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    from_port["name"],
                    to_port["name"],
                    from_port["x"],
                    from_port["y"],
                    to_port["x"],
                    to_port["y"],
                    MapLinkType.CHARTER_SHIP.value,
                    f"Charter ship: {from_port['name']} -> {to_port['name']}",
                ),
            )
            link_count += 1

    conn.commit()
    print(f"Inserted {link_count} charter ship links into {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch charter ship map links")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
