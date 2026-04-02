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
COORD_XY_PARAM = re.compile(r"\|x\s*=\s*(\d+)\|y\s*=\s*(\d+)")
COORD_XY_COLON = re.compile(r"x:(\d+),y:(\d+)")
COORD_POSITIONAL = re.compile(r"\|(\d{3,5}),(\d{3,5})")

FACILITY_PAGES = {
    Facility.BANK: "List_of_banks",
    Facility.FURNACE: "Furnace",
    Facility.ANVIL: "Anvil",
    Facility.ALTAR: "Altar/Locations",
    Facility.SPINNING_WHEEL: "Spinning_wheel",
    Facility.LOOM: "Loom",
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

    Handles both {{Map}} templates in table rows and {{ObjectLocLine}} templates.
    Returns list of (x, y, name) tuples.
    """
    entries: list[tuple[int, int, str | None]] = []

    # Method 1: Map templates in table rows
    for row in wikitext.split("|-"):
        map_matches = list(re.finditer(r"\{\{Map[^}]*\}\}", row))
        if not map_matches:
            continue

        name = None
        name_match = re.search(r"\[\[([^]|]+?)(?:\|[^]]+)?\]\]", row)
        if name_match:
            name = name_match.group(1).strip()

        for map_match in map_matches:
            coords = extract_coords_from_map(map_match.group(0))
            for x, y in coords:
                entries.append((x, y, name))

    # Method 2: ObjectLocLine templates (multiline, used by spinning wheels etc.)
    i = 0
    while i < len(wikitext):
        if wikitext[i:i + 15] == "{{ObjectLocLine":
            depth = 0
            start = i
            while i < len(wikitext):
                if wikitext[i:i + 2] == "{{":
                    depth += 1
                    i += 2
                elif wikitext[i:i + 2] == "}}":
                    depth -= 1
                    i += 2
                    if depth == 0:
                        block = wikitext[start:i]
                        name_match = re.search(r"\|location\s*=\s*\[\[([^]|]+?)(?:\|[^]]+)?\]\]", block)
                        name = name_match.group(1).strip() if name_match else None
                        coords = extract_coords_from_map(block)
                        for x, y in coords:
                            entries.append((x, y, name))
                        break
                else:
                    i += 1
        else:
            i += 1

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
