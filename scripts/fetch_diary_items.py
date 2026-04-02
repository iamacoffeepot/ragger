"""Fetch diary task item requirements from the Achievement Diary overview page.

Uses the structured tables on the Achievement Diary page which have a curated
"Items required" column, then cross-references against the items table.

Requires: fetch_items.py and fetch_diary_tasks.py to have been run first.
"""

import argparse
import re
from pathlib import Path

from clogger.db import create_tables, get_connection
from clogger.wiki import fetch_page_wikitext_with_attribution, link_requirement, strip_markup

# Pattern to extract wiki links from item text
ITEM_LINK_PATTERN = re.compile(r"\[\[([^]|]+?)(?:\|([^]]+))?\]\]")

# Map wiki diary names to our enum values
DIARY_NAME_MAP = {
    "Ardougne": "Ardougne",
    "Desert": "Desert",
    "Falador": "Falador",
    "Fremennik": "Fremennik",
    "Kandarin": "Kandarin",
    "Karamja": "Karamja",
    "Kourend & Kebos": "Kourend & Kebos",
    "Kourend": "Kourend & Kebos",
    "Lumbridge & Draynor": "Lumbridge & Draynor",
    "Lumbridge": "Lumbridge & Draynor",
    "Morytania": "Morytania",
    "Varrock": "Varrock",
    "Western Provinces": "Western Provinces",
    "Western": "Western Provinces",
    "Wilderness": "Wilderness",
}

TIER_MAP = {
    "1": "Easy",
    "2": "Medium",
    "3": "Hard",
    "4": "Elite",
}


def parse_diary_item_requirements(wikitext: str) -> list[tuple[str, str, str, list[str]]]:
    """Parse the Achievement Diary page tables.

    Returns list of (description, location, tier, [item_names]) tuples.
    """
    results: list[tuple[str, str, str, list[str]]] = []

    tables = wikitext.split("{|")
    for table in tables:
        if "Items required" not in table:
            continue

        rows = table.split("|-")
        for row in rows:
            cells = re.split(r"\n\|", row)
            if len(cells) < 7:
                continue

            # Columns: [0]=empty, [1]=Task, [2]=Quest(s), [3]=Skill(s), [4]=Items, [5]=Diary, [6]=Difficulty
            items_cell = cells[4]
            diary_cell = cells[5]
            difficulty_cell = cells[6]

            # Skip if no items or "None"
            if "{{NA|" in items_cell or not items_cell.strip():
                continue

            # Extract task description
            description = strip_markup(cells[1])
            description = re.sub(r"\s+", " ", description).strip()
            if not description:
                continue

            # Extract diary location
            diary_match = re.search(r"\[\[([^]]+?)(?:\|([^]]+))?\]\]", diary_cell)
            if diary_match:
                raw_diary = (diary_match.group(2) or diary_match.group(1)).replace(" Diary", "").strip()
                location = DIARY_NAME_MAP.get(raw_diary, raw_diary)
            else:
                continue

            # Extract difficulty
            tier_match = re.search(r"data-sort-value=(\d)", difficulty_cell)
            if tier_match:
                tier = TIER_MAP.get(tier_match.group(1), "")
            else:
                tier_text = strip_markup(difficulty_cell).strip()
                tier = tier_text if tier_text in ("Easy", "Medium", "Hard", "Elite") else ""
            if not tier:
                continue

            # Extract item names from links
            item_names: list[str] = []
            for match in ITEM_LINK_PATTERN.finditer(items_cell):
                item_name = match.group(1).strip()
                if item_name.startswith("File:") or item_name.startswith("Category:"):
                    continue
                if "#" in item_name:
                    continue
                if item_name not in item_names:
                    item_names.append(item_name)

            if item_names:
                results.append((description, location, tier, item_names))

    return results


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    # Items table is the source of truth
    item_ids = dict(conn.execute("SELECT name, id FROM items").fetchall())

    # Build diary task lookup: (location, tier, description) -> id
    diary_tasks = {}
    for row in conn.execute("SELECT id, location, tier, description FROM diary_tasks").fetchall():
        diary_tasks[(row[1], row[2], row[3])] = row[0]

    print("Fetching Achievement Diary page...")
    wikitext = fetch_page_wikitext_with_attribution(conn, "Achievement Diary", "diary_task_item_requirements")
    parsed = parse_diary_item_requirements(wikitext)

    matched = 0
    unmatched = 0
    item_req_count = 0

    for description, location, tier, item_names in parsed:
        # Try to find matching diary task — fuzzy match on description start
        diary_task_id = None
        for (loc, t, desc), tid in diary_tasks.items():
            if loc == location and t == tier and description[:30].lower() in desc[:30].lower():
                diary_task_id = tid
                break

        if diary_task_id is None:
            unmatched += 1
            continue
        matched += 1

        for item_name in item_names:
            item_id = item_ids.get(item_name)
            if item_id is None:
                continue
            link_requirement(
                conn,
                table="item_requirements",
                columns={"item_id": item_id, "quantity": 1},
                junction_table="diary_task_item_requirements",
                entity_column="diary_task_id",
                entity_id=diary_task_id,
                requirement_column="item_requirement_id",
            )
            item_req_count += 1

    conn.commit()
    print(f"Matched {matched} tasks, {unmatched} unmatched, {item_req_count} item requirements inserted into {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch diary task item requirements")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/clogger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
