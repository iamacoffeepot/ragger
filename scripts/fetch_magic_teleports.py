"""Fetch all teleport destinations and create map links.

Covers spell teleports (Standard, Ancient, Lunar) and item teleports
(jewellery, special items). All use from_location="ANYWHERE".
"""

import argparse
import re
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.enums import MAP_LINK_ANYWHERE, MapLinkType
from ragger.wiki import (
    extract_coords,
    fetch_pages_wikitext_batch,
    record_attributions_batch,
    strip_wiki_links,
)

TELEPORT_LINE = re.compile(r"\{\{TeleportLocationLine\|name=(?:\d+\.\s*)?\[\[([^\]|]+).*?\|x=(\d+)\|y=(\d+)")

# Spell pages: single destination per page
SPELL_TELEPORTS = [
    # Standard spellbook
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
    # Ancient Magicks
    "Paddewwa Teleport",
    "Senntisten Teleport",
    "Kharyrll Teleport",
    "Lassar Teleport",
    "Dareeyak Teleport",
    "Carrallanger Teleport",
    "Annakarl Teleport",
    "Ghorrock Teleport",
    # Lunar spellbook
    "Moonclan Teleport",
    "Ourania Teleport",
    "Waterbirth Teleport",
    "Barbarian Teleport",
    "Khazard Teleport",
    "Fishing Guild Teleport",
    "Catherby Teleport",
    "Ice Plateau Teleport",
]

# Item pages: multiple destinations per page via {{TeleportLocationLine}}
ITEM_TELEPORTS = [
    "Ring of dueling",
    "Games necklace",
    "Combat bracelet",
    "Skills necklace",
    "Amulet of glory",
    "Ring of wealth",
    "Slayer ring",
    "Digsite pendant",
    "Necklace of passage",
    "Burning amulet",
    "Xeric's talisman",
    "Drakan's medallion",
]


def extract_first_coord(wikitext: str) -> tuple[int, int] | None:
    coords = extract_coords(wikitext)
    return coords[0] if coords else None


def extract_level(wikitext: str) -> int | None:
    match = re.search(r"\|level\s*=\s*(\d+)", wikitext)
    return int(match.group(1)) if match else None


def extract_destination(wikitext: str, spell_name: str) -> str:
    match = re.search(r"[Tt]eleports?\s+(?:the\s+)?(?:caster|player)\s+to\s+(?:the\s+)?(?:[\w\s]*?)?\[\[([^\]|]+)", wikitext)
    if match:
        return match.group(1).strip()
    return spell_name.replace(" Teleport", "")


def parse_item_teleports(wikitext: str) -> list[tuple[str, int, int]]:
    """Parse teleport destinations from an item page.

    Handles {{TeleportLocationLine}} templates and wikitable rows with
    [[Location]] + {{Map|x=...|y=...}} format.

    Returns list of (destination_name, x, y).
    """
    results: list[tuple[str, int, int]] = []

    # Method 1: TeleportLocationLine templates
    for match in TELEPORT_LINE.finditer(wikitext):
        results.append((match.group(1).strip(), int(match.group(2)), int(match.group(3))))

    if results:
        return results

    # Method 2: Wikitable rows with [[Location]] and {{Map|x=|y=}}
    rows = wikitext.split("|-")
    for row in rows:
        name_match = re.search(r"^\|?\s*\[\[([^\]|]+)", row.strip())
        x_match = re.search(r"\|x=(\d+)", row)
        y_match = re.search(r"\|y=(\d+)", row)
        if name_match and x_match and y_match:
            results.append((name_match.group(1).strip(), int(x_match.group(1)), int(y_match.group(1))))

    return results


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    all_pages = SPELL_TELEPORTS + ITEM_TELEPORTS
    print(f"Fetching {len(all_pages)} teleport pages...")
    all_wikitext = fetch_pages_wikitext_batch(all_pages)

    link_count = 0
    found_pages: list[str] = []

    # Spell teleports: single destination per page
    for spell_name in SPELL_TELEPORTS:
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
               (src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (MAP_LINK_ANYWHERE, destination, 0, 0, coord[0], coord[1],
             MapLinkType.TELEPORT.value, f"{spell_name}{level_note}"),
        )
        link_count += 1
        found_pages.append(spell_name)
        print(f"  {spell_name}: -> {destination} ({coord[0]}, {coord[1]}){level_note}")

    # Item teleports: multiple destinations per page
    for item_name in ITEM_TELEPORTS:
        wikitext = all_wikitext.get(item_name, "")
        if not wikitext:
            print(f"  Warning: page not found for '{item_name}'")
            continue

        destinations = parse_item_teleports(wikitext)
        if not destinations:
            print(f"  Warning: no teleport destinations for '{item_name}'")
            continue

        for dest_name, x, y in destinations:
            conn.execute(
                """INSERT INTO map_links
                   (src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (MAP_LINK_ANYWHERE, dest_name, 0, 0, x, y,
                 MapLinkType.TELEPORT.value, f"{item_name}: {dest_name}"),
            )
            link_count += 1
            print(f"  {item_name}: -> {dest_name} ({x}, {y})")

        found_pages.append(item_name)

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
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
