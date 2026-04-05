"""Fetch activity data from the OSRS wiki.

Parses {{Infobox Activity}} for name, type, members, location, players,
skills, and region. Skills are stored as a bitmask.

Uses batched API calls (50 pages per request).
"""

import argparse
import re
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.enums import COMBAT_SKILLS_MASK, ALL_SKILLS_MASK, ActivityType, Skill
from ragger.wiki import (
    extract_template,
    fetch_category_members,
    fetch_pages_wikitext_batch,
    parse_template_param,
    record_attributions_batch,
    resolve_region,
    strip_wiki_links,
)


def parse_skills_mask(raw: str | None) -> int:
    """Convert a skills field like '[[Fishing]], [[Combat]]' to a bitmask."""
    if not raw:
        return 0

    text = strip_wiki_links(raw).strip()
    if not text or text.lower() == "none":
        return 0

    # "All skills" or similar
    if "all skill" in text.lower():
        return ALL_SKILLS_MASK

    mask = 0
    parts = re.split(r"[,;]+", text)
    for part in parts:
        name = part.strip()
        if not name:
            continue
        lower = name.lower()
        if lower == "combat":
            mask |= COMBAT_SKILLS_MASK
        elif lower == "skilling":
            mask |= ALL_SKILLS_MASK & ~COMBAT_SKILLS_MASK
        else:
            try:
                mask |= Skill.from_label(name).mask
            except KeyError:
                pass
    return mask


def parse_activity(wikitext: str) -> dict | None:
    """Extract activity data from an Infobox Activity."""
    block = extract_template(wikitext, "Infobox Activity")
    if not block:
        return None

    name = parse_template_param(block, "name")
    raw_type = parse_template_param(block, "type") or ""
    activity_type = ActivityType.from_label(raw_type)

    members_raw = parse_template_param(block, "members") or ""
    members = 0 if members_raw.strip().lower() == "no" else 1

    location = parse_template_param(block, "location")
    if location:
        location = strip_wiki_links(location).strip()

    players = parse_template_param(block, "players")
    if players:
        players = strip_wiki_links(players).strip()

    skills_raw = parse_template_param(block, "skills")
    skills = parse_skills_mask(skills_raw)

    league_region = parse_template_param(block, "leagueRegion")
    region = resolve_region(league_region)

    return {
        "name": name,
        "type": activity_type,
        "members": members,
        "location": location,
        "players": players,
        "skills": skills,
        "region": region,
    }


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    pages = fetch_category_members("Activities")
    print(f"Found {len(pages)} activity pages...")

    count = 0

    for i in range(0, len(pages), 50):
        batch = pages[i:i + 50]
        wikitext_batch = fetch_pages_wikitext_batch(batch)

        for page_name, wikitext in wikitext_batch.items():
            if not wikitext:
                continue

            data = parse_activity(wikitext)
            if not data:
                continue

            display_name = data["name"] or page_name

            conn.execute(
                """INSERT OR IGNORE INTO activities
                   (name, type, members, location, players, skills, region)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    display_name,
                    data["type"].value,
                    data["members"],
                    data["location"],
                    data["players"],
                    data["skills"],
                    data["region"],
                ),
            )
            count += 1

    print("Recording attributions...")
    record_attributions_batch(conn, "activities", pages)

    conn.commit()
    print(f"Inserted {count} activities into {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch OSRS activity data")
    parser.add_argument("--db", type=Path, default=Path("data/ragger.db"))
    args = parser.parse_args()
    ingest(args.db)
