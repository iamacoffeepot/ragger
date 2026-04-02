"""Fetch location data from the OSRS wiki and populate locations/location_adjacencies tables.

Parses {{Infobox Location}} for metadata and {{Relativelocation}} / {{Relative location}}
for adjacency data.
"""

import argparse
import re
from pathlib import Path

from clogger.db import create_tables, get_connection
from clogger.enums import Region
from clogger.wiki import (
    extract_template,
    fetch_category_members,
    fetch_page_wikitext,
    parse_template_param,
    strip_wiki_links,
    throttle,
)

DIRECTIONS = ("north", "south", "east", "west")

POSITIONAL_COORDS_PATTERN = re.compile(r"\|(\d{3,5}),(\d{3,5})")


def parse_map_coords(wikitext: str) -> tuple[int | None, int | None]:
    """Extract x,y tile coordinates from the {{Map}} template."""
    i = 0
    map_text = None
    while i < len(wikitext):
        if wikitext[i:i + 5] == "{{Map":
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
                        map_text = wikitext[start:i]
                        break
                else:
                    i += 1
            break
        else:
            i += 1

    if not map_text:
        return None, None

    x_match = re.search(r"\|x=(\d+)", map_text)
    y_match = re.search(r"\|y=(\d+)", map_text)
    if x_match and y_match:
        return int(x_match.group(1)), int(y_match.group(1))

    pos_match = POSITIONAL_COORDS_PATTERN.search(map_text)
    if pos_match:
        return int(pos_match.group(1)), int(pos_match.group(2))

    return None, None


def resolve_region(label: str | None) -> int | None:
    if not label:
        return None
    cleaned = re.sub(r"<!--.*?-->", "", label).strip().lower()
    if cleaned in ("no", "n/a", "none", ""):
        return None
    first_group = label.split(",")[0].strip()
    first_region = first_group.split("&")[0].strip()
    try:
        return Region.from_label(first_region).value
    except KeyError:
        return None


def parse_infobox_location(wikitext: str, page: str) -> dict | None:
    block = extract_template(wikitext, "Infobox Location")
    if not block:
        return None

    name = parse_template_param(block, "name")
    if not name:
        print(f"  Warning: no name in Infobox Location for page '{page}'")
        return None

    location_str = parse_template_param(block, "location")
    league_region = parse_template_param(block, "leagueRegion")
    loc_type = parse_template_param(block, "type")
    members_str = parse_template_param(block, "members")

    region = resolve_region(league_region)
    if region is None and league_region:
        print(f"  Warning: unhandled leagueRegion '{league_region}' for '{name}'")

    if loc_type:
        loc_type = strip_wiki_links(loc_type).strip()

    members = 0 if members_str and members_str.strip().lower() == "no" else 1

    x, y = parse_map_coords(wikitext)

    return {
        "name": name,
        "region": region,
        "type": loc_type,
        "members": members,
        "x": x,
        "y": y,
    }


def parse_adjacency(wikitext: str, page: str) -> dict[str, str]:
    adjacency: dict[str, str] = {}

    # Try both template name variants
    block = extract_template(wikitext, "Relativelocation")
    if block is None:
        block = extract_template(wikitext, "Relative location")
    if block is None:
        return adjacency

    for direction in DIRECTIONS:
        value = parse_template_param(block, direction)
        if value:
            cleaned = strip_wiki_links(value).strip()
            if cleaned:
                adjacency[direction] = cleaned
            else:
                print(f"  Warning: empty {direction} adjacency after cleanup for '{page}'")

    return adjacency


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    pages = fetch_category_members("Locations")
    print(f"Found {len(pages)} pages in Category:Locations")

    location_count = 0
    adjacency_count = 0
    skipped = 0

    for page in pages:
        wikitext = fetch_page_wikitext(page)

        infobox = parse_infobox_location(wikitext, page)
        if not infobox:
            skipped += 1
            continue

        conn.execute(
            "INSERT OR IGNORE INTO locations (name, region, type, members, x, y) VALUES (?, ?, ?, ?, ?, ?)",
            (infobox["name"], infobox["region"], infobox["type"], infobox["members"], infobox["x"], infobox["y"]),
        )
        loc_row = conn.execute("SELECT id FROM locations WHERE name = ?", (infobox["name"],)).fetchone()
        if not loc_row:
            continue
        loc_id = loc_row[0]

        adjacency = parse_adjacency(wikitext, page)
        for direction, neighbor in adjacency.items():
            conn.execute(
                "INSERT OR IGNORE INTO location_adjacencies (location_id, direction, neighbor) VALUES (?, ?, ?)",
                (loc_id, direction, neighbor),
            )
            adjacency_count += 1

        location_count += 1
        throttle()

    conn.commit()
    print(f"Inserted {location_count} locations with {adjacency_count} adjacency edges ({skipped} pages skipped) into {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch OSRS location data")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/clogger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
