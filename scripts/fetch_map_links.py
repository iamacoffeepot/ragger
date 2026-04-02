"""Extract entrance/exit map links from location pages.

Sweeps all locations in batches, looks for multiple {{Map}} templates,
and extracts surface-to-underground connections.

Requires: fetch_locations.py to have been run first.
"""

import argparse
import re
from pathlib import Path

from clogger.db import create_tables, get_connection
from clogger.wiki import fetch_pages_wikitext_batch, record_attributions_batch

COORD_XY_PARAM = re.compile(r"\|x\s*=\s*(\d+)")
COORD_Y_PARAM = re.compile(r"\|y\s*=\s*(\d+)")
COORD_XY_COLON = re.compile(r"x:(\d+),y:(\d+)")
COORD_POSITIONAL = re.compile(r"\|(\d{3,5}),(\d{3,5})")


def extract_all_maps(wikitext: str) -> list[dict]:
    """Extract all {{Map}} templates with their coordinates and captions."""
    maps: list[dict] = []
    i = 0
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
                        block = wikitext[start:i]

                        # Extract caption
                        caption = ""
                        cap_match = re.search(r"caption=([^|}}]*)", block)
                        if cap_match:
                            caption = cap_match.group(1).strip()

                        # Extract coordinates
                        coords: list[tuple[int, int]] = []

                        x_match = COORD_XY_PARAM.search(block)
                        y_match = COORD_Y_PARAM.search(block)
                        if x_match and y_match:
                            coords.append((int(x_match.group(1)), int(y_match.group(1))))

                        for match in COORD_XY_COLON.finditer(block):
                            coords.append((int(match.group(1)), int(match.group(2))))

                        if not coords:
                            for match in COORD_POSITIONAL.finditer(block):
                                coords.append((int(match.group(1)), int(match.group(2))))

                        if coords:
                            maps.append({
                                "caption": caption,
                                "coords": coords,
                            })
                        break
                else:
                    i += 1
        else:
            i += 1
    return maps


def classify_maps(maps: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split maps into surface and underground based on coordinates and captions."""
    surface: list[dict] = []
    underground: list[dict] = []

    for m in maps:
        caption_lower = m["caption"].lower()
        is_entrance = "entrance" in caption_lower

        # Check if any coordinate is underground (y > 5000)
        has_underground = any(y > 5000 for _, y in m["coords"])
        has_surface = any(y <= 5000 for _, y in m["coords"])

        if is_entrance or (has_surface and not has_underground):
            surface.append(m)
        elif has_underground:
            underground.append(m)

    return surface, underground


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    pages = [row[0] for row in conn.execute("SELECT name FROM locations ORDER BY name").fetchall()]
    print(f"Scanning {len(pages)} locations for map links...")

    link_count = 0
    linked_pages: list[str] = []

    for i in range(0, len(pages), 50):
        batch = pages[i:i + 50]
        print(f"  Batch {i + 1}-{i + len(batch)}...")
        wikitext_batch = fetch_pages_wikitext_batch(batch)

        for page_name, wikitext in wikitext_batch.items():
            maps = extract_all_maps(wikitext)
            if len(maps) < 2:
                continue

            surface, underground = classify_maps(maps)
            if not surface or not underground:
                continue

            # Get the infobox location field for the parent location name
            loc_match = re.search(r"\|location\s*=\s*\[\[([^\]|]+)", wikitext)
            parent = loc_match.group(1).strip() if loc_match else None

            # Create links: surface entrance -> underground location
            for s in surface:
                for u in underground:
                    for sx, sy in s["coords"]:
                        for ux, uy in u["coords"]:
                            description = s["caption"] if s["caption"] else f"Entrance to {page_name}"
                            from_loc = parent if parent else page_name
                            # Surface -> underground
                            conn.execute(
                                """INSERT INTO map_links
                                   (from_location, to_location, from_x, from_y, to_x, to_y, type, description)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                                (from_loc, page_name, sx, sy, ux, uy, "entrance", description),
                            )
                            # Underground -> surface
                            conn.execute(
                                """INSERT INTO map_links
                                   (from_location, to_location, from_x, from_y, to_x, to_y, type, description)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                                (page_name, from_loc, ux, uy, sx, sy, "exit", f"Exit from {page_name}"),
                            )
                            link_count += 2

            linked_pages.append(page_name)

    if linked_pages:
        print("Recording attributions...")
        record_attributions_batch(conn, "map_links", linked_pages)

    conn.commit()
    print(f"Inserted {link_count} map links from {len(linked_pages)} locations into {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract map links from location pages")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/clogger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
