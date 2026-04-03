"""Fetch non-combat NPC data from the OSRS wiki.

Pulls name, versioned locations, coordinates, options, and region.
Uses batched API calls.

Excludes monsters (those are in fetch_monsters.py).
"""

import argparse
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.wiki import (
    extract_coords,
    extract_template,
    fetch_category_members,
    fetch_pages_wikitext_batch,
    parse_template_param,
    record_attributions_batch,
    resolve_region,
    strip_wiki_links,
)


def parse_npc_versions(wikitext: str) -> list[dict]:
    """Extract all versioned NPC entries from an Infobox NPC."""
    block = extract_template(wikitext, "Infobox NPC")
    if not block:
        return []

    # Detect versions
    versions: list[str] = []
    i = 1
    while True:
        if parse_template_param(block, f"version{i}") is not None:
            versions.append(str(i))
            i += 1
        else:
            break

    if not versions:
        versions = [""]

    entries = []
    for v in versions:
        name_field = parse_template_param(block, f"name{v}") or parse_template_param(block, "name")
        version_label = parse_template_param(block, f"version{v}") if v else None
        location = parse_template_param(block, f"location{v}") or parse_template_param(block, "location")
        options = parse_template_param(block, f"options{v}") or parse_template_param(block, "options")
        league_region = parse_template_param(block, f"leagueRegion{v}") or parse_template_param(block, "leagueRegion")

        # Extract coords from map field
        coords = []
        map_field = f"map{v}" if v else "map"
        idx = block.find(f"|{map_field}")
        if idx >= 0:
            chunk = block[idx:idx + 300]
            coords = extract_coords(chunk)

        if location:
            location = strip_wiki_links(location)

        region = resolve_region(league_region)

        x, y = (coords[0] if coords else (None, None))

        entries.append({
            "version": version_label,
            "location": location,
            "x": x,
            "y": y,
            "options": options,
            "region": region,
        })

    return entries


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    pages = fetch_category_members("Non-player characters")
    # Exclude monsters we already have
    monster_names = set(r[0] for r in conn.execute("SELECT DISTINCT name FROM monsters").fetchall())

    print(f"Found {len(pages)} NPC pages, excluding {len(monster_names)} monsters...")

    npc_count = 0

    for i in range(0, len(pages), 50):
        batch = pages[i:i + 50]
        wikitext_batch = fetch_pages_wikitext_batch(batch)

        for page_name, wikitext in wikitext_batch.items():
            if page_name in monster_names:
                continue
            if not wikitext:
                continue

            entries = parse_npc_versions(wikitext)
            for entry in entries:
                conn.execute(
                    """INSERT OR IGNORE INTO npcs
                       (name, version, location, x, y, options, region)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        page_name,
                        entry["version"],
                        entry["location"],
                        entry["x"],
                        entry["y"],
                        entry["options"],
                        entry["region"],
                    ),
                )
                npc_count += 1

        if (i + 50) % 500 == 0:
            print(f"  Processed {i + 50}/{len(pages)}...")

    print("Recording attributions...")
    record_attributions_batch(conn, "npcs", [p for p in pages if p not in monster_names])

    conn.commit()
    print(f"Inserted {npc_count} NPC entries into {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch OSRS NPC data")
    parser.add_argument("--db", type=Path, default=Path("data/ragger.db"))
    args = parser.parse_args()
    ingest(args.db)
