"""Link quests to items by parsing |items = fields and navbox templates.

Sources:
  1. |items = field from {{Quest details}} on quest pages — required items
  2. {{plink|...}} entries in the Items section of Template:<Quest> navboxes — all quest items

Requires: fetch_items.py and fetch_quests.py to have been run first.
"""

import argparse
import re
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.wiki import fetch_page_wikitext, throttle

# Matches [[Item name]] or [[Item name|display]]
ITEM_LINK_PATTERN = re.compile(r"\[\[([^]|]+?)(?:\|[^]]+)?\]\]")
# Matches {{plink|Item name}} or {{plink|Item name|txt=...}} etc.
PLINK_PATTERN = re.compile(r"\{\{plink\|([^}|]+?)(?:\|[^}]*)?\}\}")

# Names that are not real items (skills, concepts, etc.)
SKIP_NAMES = {
    "experience", "quest", "quests", "slayer", "hitpoints", "attack", "strength",
    "defence", "ranged", "prayer", "magic", "runecraft", "construction", "agility",
    "herblore", "thieving", "crafting", "fletching", "hunter", "mining", "smithing",
    "fishing", "cooking", "firemaking", "woodcutting", "farming", "combat",
    "free-to-play", "member", "members", "coins", "wilderness",
    "quest points", "quest point", "barbarian training",
}


def extract_items_field(wikitext: str) -> str | None:
    """Extract the |items = field from {{Quest details}} template."""
    lines = wikitext.split("\n")
    result: list[str] = []
    capturing = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|items"):
            capturing = True
            after_eq = stripped.split("=", 1)
            if len(after_eq) > 1:
                result.append(after_eq[1])
        elif capturing:
            if stripped.startswith("|") or stripped.startswith("}}"):
                break
            result.append(line)
    return "\n".join(result).strip() if result else None


def parse_items_field(items_text: str) -> set[str]:
    """Extract unique item names from the |items = field."""
    names: set[str] = set()
    for line in items_text.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("*") or stripped.startswith("**"):
            continue
        for match in ITEM_LINK_PATTERN.finditer(stripped):
            name = match.group(1).strip()
            if name.lower() in SKIP_NAMES or name.startswith("File:"):
                continue
            names.add(name)
    return names


def parse_navbox_items(navbox_text: str) -> set[str]:
    """Extract item names from {{plink|...}} in the Items section of a navbox."""
    names: set[str] = set()
    in_items = False
    for line in navbox_text.split("\n"):
        # Enter items section
        if "gtitle" in line and "Items" in line:
            in_items = True
            continue
        # Exit items section at next non-items group title
        if in_items and "gtitle" in line and "Items" not in line and "Key" not in line:
            in_items = False
            continue
        if in_items:
            for match in PLINK_PATTERN.finditer(line):
                name = match.group(1).strip()
                if name.lower() in SKIP_NAMES:
                    continue
                names.add(name)
    return names


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    quest_rows = conn.execute("SELECT id, name FROM quests").fetchall()
    item_ids = dict(conn.execute("SELECT name, id FROM items").fetchall())
    item_ids_lower = {k.lower(): v for k, v in item_ids.items()}

    conn.execute("DELETE FROM quest_items")

    total_links = 0
    total_unmatched = 0
    quests_with_items = 0

    def resolve_and_insert(quest_id: int, names: set[str]) -> tuple[int, int]:
        linked = 0
        unmatched = 0
        for name in names:
            iid = item_ids.get(name) or item_ids_lower.get(name.lower())
            if iid is not None:
                conn.execute(
                    "INSERT OR IGNORE INTO quest_items (quest_id, item_id) VALUES (?, ?)",
                    (quest_id, iid),
                )
                linked += 1
            else:
                unmatched += 1
        return linked, unmatched

    for quest_id, quest_name in quest_rows:
        all_items: set[str] = set()

        # Source 1: |items = field from quest page
        wikitext = fetch_page_wikitext(quest_name)
        if wikitext:
            items_field = extract_items_field(wikitext)
            if items_field:
                all_items |= parse_items_field(items_field)
        throttle()

        # Source 2: navbox template
        navbox = fetch_page_wikitext(f"Template:{quest_name}")
        if navbox:
            all_items |= parse_navbox_items(navbox)
        throttle()

        if all_items:
            linked, unmatched = resolve_and_insert(quest_id, all_items)
            total_links += linked
            total_unmatched += unmatched
            quests_with_items += 1

    conn.commit()
    print(
        f"Linked {total_links} items to {quests_with_items} quests "
        f"({total_unmatched} unmatched) from {len(quest_rows)} total quests"
    )
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Link quests to items from wiki")
    parser.add_argument("--db", type=Path, default=Path("data/ragger.db"))
    args = parser.parse_args()
    ingest(args.db)
