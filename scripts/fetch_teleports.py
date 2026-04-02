"""Fetch standard spellbook teleport destinations and create map links.

Teleports have from_location="ANYWHERE" since they can be cast from any location.
"""

import argparse
import re
from pathlib import Path

from clogger.db import create_tables, get_connection
from clogger.enums import MAP_LINK_ANYWHERE, MapLinkType
from clogger.wiki import (
    fetch_pages_wikitext_batch,
    record_attributions_batch,
)

COORD_POSITIONAL = re.compile(r"\|(\d{3,5}),(\d{3,5})")
COORD_XY_PARAM = re.compile(r"\|x\s*=\s*(\d+)")
COORD_Y_PARAM = re.compile(r"\|y\s*=\s*(\d+)")

# Standard spellbook teleports: page name -> destination location name
STANDARD_TELEPORTS = [
    "Varrock Teleport",
    "Lumbridge Teleport",
    "Falador Teleport",
    "Camelot Teleport",
    "Kourend Castle Teleport",
    "Ardougne Teleport",
    "Civitas illa Fortis Teleport",
    "Watchtower Teleport",
    "Trollheim Teleport",
    "Ape Atoll Teleport",
]


def extract_first_coord(wikitext: str) -> tuple[int, int] | None:
    """Extract the first coordinate pair from a spell page."""
    match = COORD_POSITIONAL.search(wikitext)
    if match:
        return int(match.group(1)), int(match.group(2))

    x_match = COORD_XY_PARAM.search(wikitext)
    y_match = COORD_Y_PARAM.search(wikitext)
    if x_match and y_match:
        return int(x_match.group(1)), int(y_match.group(1))

    return None


def extract_level(wikitext: str) -> int | None:
    match = re.search(r"\|level\s*=\s*(\d+)", wikitext)
    return int(match.group(1)) if match else None


def extract_destination(wikitext: str, spell_name: str) -> str:
    """Try to extract the destination location name from the spell page."""
    # Look for "Teleports the caster to [[Location]]" pattern
    match = re.search(r"[Tt]eleports?\s+(?:the\s+)?(?:caster|player)\s+to\s+(?:the\s+)?(?:[\w\s]*?)?\[\[([^\]|]+)", wikitext)
    if match:
        return match.group(1).strip()
    # Fallback: derive from spell name
    return spell_name.replace(" Teleport", "")


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    print("Fetching teleport spell data...")
    all_wikitext = fetch_pages_wikitext_batch(STANDARD_TELEPORTS)

    link_count = 0
    found_pages: list[str] = []

    for spell_name in STANDARD_TELEPORTS:
        wikitext = all_wikitext.get(spell_name, "")
        if not wikitext:
            print(f"  Warning: page not found for '{spell_name}'")
            continue

        coord = extract_first_coord(wikitext)
        if not coord:
            print(f"  Warning: no coordinates for '{spell_name}'")
            continue

        level = extract_level(wikitext)
        destination = extract_destination(wikitext, spell_name)

        level_note = f" (Magic {level})" if level else ""
        conn.execute(
            """INSERT INTO map_links
               (from_location, to_location, from_x, from_y, to_x, to_y, type, description)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                MAP_LINK_ANYWHERE,
                destination,
                0,
                0,
                coord[0],
                coord[1],
                MapLinkType.TELEPORT.value,
                f"{spell_name}{level_note}",
            ),
        )
        link_count += 1
        found_pages.append(spell_name)
        print(f"  {spell_name}: -> {destination} ({coord[0]}, {coord[1]}){level_note}")

    if found_pages:
        print("Recording attributions...")
        record_attributions_batch(conn, "map_links", found_pages)

    conn.commit()
    print(f"Inserted {link_count} teleport links into {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch teleport spell map links")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/clogger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
