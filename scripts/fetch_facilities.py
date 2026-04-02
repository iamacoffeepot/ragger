"""Fetch facility data (banks, furnaces, anvils, altars) from wiki list pages.

Parses coordinates from {{Map}} templates and stores them in the facilities table.
"""

import argparse
import re
from pathlib import Path

from clogger.db import create_tables, get_connection
from clogger.enums import Facility
from clogger.wiki import fetch_page_wikitext

# Map template coordinate patterns
COORD_XY_PARAM = re.compile(r"\|x=(\d+)\|y=(\d+)")
COORD_XY_COLON = re.compile(r"x:(\d+),y:(\d+)")
COORD_POSITIONAL = re.compile(r"\|(\d{3,5}),(\d{3,5})")

FACILITY_PAGES = {
    Facility.BANK: "List_of_banks",
    Facility.FURNACE: "Furnace",
    Facility.ANVIL: "Anvil",
    Facility.ALTAR: "Altar",
}


def extract_coords_from_map(text: str) -> list[tuple[int, int]]:
    """Extract all x,y coordinate pairs from Map template text."""
    coords: list[tuple[int, int]] = []

    match = COORD_XY_PARAM.search(text)
    if match:
        coords.append((int(match.group(1)), int(match.group(2))))
        return coords

    for match in COORD_XY_COLON.finditer(text):
        coords.append((int(match.group(1)), int(match.group(2))))
    if coords:
        return coords

    match = COORD_POSITIONAL.search(text)
    if match:
        coords.append((int(match.group(1)), int(match.group(2))))

    return coords


def parse_facility_entries(wikitext: str) -> list[tuple[int, int, str | None]]:
    """Extract facility coordinates and optional names from wiki page tables.

    Returns list of (x, y, name) tuples.
    """
    entries: list[tuple[int, int, str | None]] = []

    # Split into table rows
    for row in wikitext.split("|-"):
        # Find Map templates in this row
        map_matches = list(re.finditer(r"\{\{Map[^}]*\}\}", row))
        if not map_matches:
            continue

        # Try to extract a name from the first cell with a wiki link
        name = None
        name_match = re.search(r"\[\[([^]|]+?)(?:\|[^]]+)?\]\]", row)
        if name_match:
            name = name_match.group(1).strip()

        for map_match in map_matches:
            coords = extract_coords_from_map(map_match.group(0))
            for x, y in coords:
                entries.append((x, y, name))

    return entries


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    total = 0
    for facility, page in FACILITY_PAGES.items():
        print(f"\n=== {facility.label} ({page}) ===")
        wikitext = fetch_page_wikitext(page)
        entries = parse_facility_entries(wikitext)
        print(f"  Found {len(entries)} entries")

        for x, y, name in entries:
            conn.execute(
                "INSERT INTO facilities (type, x, y, name) VALUES (?, ?, ?, ?)",
                (facility.value, x, y, name),
            )

        total += len(entries)

    conn.commit()
    print(f"\nInserted {total} facilities into {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch facility data from wiki")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/clogger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
