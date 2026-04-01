"""Fetch quest-to-region mappings from quest infobox leagueRegion fields.

Parses the leagueRegion field from each quest's wiki page to determine
which regions are required to access/complete the quest.

Requires: fetch_quests.py to have been run first.
"""

import argparse
import re
import time
from pathlib import Path

import requests

from clogger.db import create_tables, get_connection
from clogger.enums import Region

API_URL = "https://oldschool.runescape.wiki/api.php"
USER_AGENT = "clogger/0.1 - OSRS Leagues planner"
HEADERS = {"User-Agent": USER_AGENT}

REGION_REQ_PATTERN = re.compile(r"\{\{RE\|(\w[\w\s]*)\}\}")


def parse_league_region(wikitext: str) -> int:
    """Extract region bitmask from the leagueRegion field.

    Uses explicit 'location requirement' lines first. If none exist,
    falls back to auto-complete region only if there's exactly one.
    """
    match = re.search(r"\|leagueRegion\s*=\s*(.*?)(?:\n\||\Z)", wikitext, re.DOTALL)
    if not match:
        return 0

    field = match.group(1)

    # First: explicit location requirements
    location_mask = 0
    for line in field.split("\n"):
        if "location requirement" in line.lower():
            for region_match in REGION_REQ_PATTERN.finditer(line):
                try:
                    region = Region.from_label(region_match.group(1).strip())
                    location_mask |= region.mask
                except KeyError:
                    pass

    if location_mask:
        return location_mask

    # Fallback: if exactly one auto-complete region, treat it as the location
    auto_regions: list[Region] = []
    for line in field.split("\n"):
        if "auto-complete" in line.lower() or "will auto-complete" in line.lower():
            for region_match in REGION_REQ_PATTERN.finditer(line):
                try:
                    region = Region.from_label(region_match.group(1).strip())
                    if region not in auto_regions:
                        auto_regions.append(region)
                except KeyError:
                    pass

    if auto_regions:
        return auto_regions[0].mask

    # Final fallback: first bare region reference
    for region_match in REGION_REQ_PATTERN.finditer(field):
        try:
            return Region.from_label(region_match.group(1).strip()).mask
        except KeyError:
            pass

    return 0


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    quest_ids = dict(conn.execute("SELECT name, id FROM quests").fetchall())

    print(f"Fetching leagueRegion for {len(quest_ids)} quests...")
    req_count = 0
    no_region = 0

    for quest_name, quest_id in quest_ids.items():
        resp = requests.get(
            API_URL,
            params={"action": "parse", "page": quest_name, "prop": "wikitext", "format": "json"},
            headers=HEADERS,
        )
        resp.raise_for_status()
        wikitext = resp.json().get("parse", {}).get("wikitext", {}).get("*", "")

        mask = parse_league_region(wikitext)
        if mask == 0:
            no_region += 1
            continue

        conn.execute(
            "INSERT OR IGNORE INTO region_requirements (regions, any_region) VALUES (?, ?)",
            (mask, 0),
        )
        req_id = conn.execute(
            "SELECT id FROM region_requirements WHERE regions = ? AND any_region = 0",
            (mask,),
        ).fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO quest_region_requirements (quest_id, region_requirement_id) VALUES (?, ?)",
            (quest_id, req_id),
        )
        req_count += 1
        time.sleep(0.1)

    conn.commit()
    print(f"Inserted {req_count} quest region requirements ({no_region} quests have no region data)")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch quest-to-region mappings")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/clogger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
