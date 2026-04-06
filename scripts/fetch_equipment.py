"""Fetch equipment data from the OSRS wiki and populate the equipment table.

Parses {{Infobox Bonuses}} for combat stats and {{Infobox Item}} for metadata.
Uses batched API calls for efficiency.

Requires: fetch_items.py to have been run first (for item_id cross-referencing).
"""

import argparse
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.enums import CombatStyle, EquipmentSlot
from ragger.wiki import (
    extract_template,
    fetch_category_members,
    fetch_pages_wikitext_batch,
    parse_template_param,
    record_attributions_batch,
    strip_wiki_links,
)


def parse_versioned_param(block: str, param: str, version: str) -> str | None:
    """Try versioned param first (e.g. astab1), then unversioned."""
    val = parse_template_param(block, f"{param}{version}")
    if val is None:
        val = parse_template_param(block, param)
    return val


def parse_int(val: str | None) -> int | None:
    if not val:
        return None
    val = val.strip().replace(",", "").replace("+", "").replace("%", "")
    try:
        return int(val)
    except ValueError:
        return None


def parse_float(val: str | None) -> float | None:
    if not val:
        return None
    val = val.strip().replace(",", "").replace("kg", "").strip()
    try:
        return float(val)
    except ValueError:
        return None


def parse_bool(val: str | None) -> int | None:
    if not val:
        return None
    cleaned = val.strip().lower()
    if cleaned in ("yes", "true", "1"):
        return 1
    if cleaned in ("no", "false", "0"):
        return 0
    return None


def get_versions(block: str) -> list[str]:
    """Detect how many versions an equipment item has."""
    versions = []
    i = 1
    while True:
        if parse_template_param(block, f"version{i}") is not None:
            versions.append(str(i))
            i += 1
        else:
            break
    if not versions:
        versions = [""]
    return versions


def parse_slot(val: str | None) -> tuple[str | None, int]:
    """Convert wiki slot value to (EquipmentSlot value, two_handed flag)."""
    if not val:
        return None, 0
    cleaned = val.strip().lower()
    two_handed = 1 if cleaned == "2h" else 0
    try:
        return EquipmentSlot.from_label(val.strip()).value, two_handed
    except ValueError:
        return None, 0


def parse_combat_style(val: str | None) -> str | None:
    """Convert wiki combatstyle value to CombatStyle enum value for storage."""
    if not val:
        return None
    try:
        return CombatStyle.from_label(val.strip()).value
    except ValueError:
        return None


def parse_equipment(name: str, wikitext: str) -> list[dict]:
    """Parse all equipment versions from a page's wikitext."""
    bonuses_block = extract_template(wikitext, "Infobox Bonuses")
    if not bonuses_block:
        return []

    item_block = extract_template(wikitext, "Infobox Item")

    # Detect versions from bonuses block first, fall back to item block
    versions = get_versions(bonuses_block)
    if versions == [""] and item_block:
        item_versions = get_versions(item_block)
        if item_versions != [""]:
            versions = item_versions

    items = []

    for v in versions:
        version_label = None
        if v:
            version_label = parse_template_param(bonuses_block, f"version{v}")
            if version_label is None and item_block:
                version_label = parse_template_param(item_block, f"version{v}")

        # Resolve item name for this version (may differ from page name)
        item_name = name
        if v and item_block:
            versioned_name = parse_template_param(item_block, f"name{v}")
            if versioned_name:
                item_name = strip_wiki_links(versioned_name)

        # Metadata from Infobox Item
        members = None
        tradeable = None
        weight = None
        game_id = None
        examine = None
        if item_block:
            members = parse_bool(parse_versioned_param(item_block, "members", v))
            tradeable = parse_bool(parse_versioned_param(item_block, "tradeable", v))
            weight = parse_float(parse_versioned_param(item_block, "weight", v))
            game_id = parse_int(parse_versioned_param(item_block, "id", v))
            examine = parse_versioned_param(item_block, "examine", v)
            if examine:
                examine = strip_wiki_links(examine)

        slot_val, two_handed = parse_slot(parse_versioned_param(bonuses_block, "slot", v))

        equipment = {
            "name": item_name,
            "version": version_label,
            "slot": slot_val,
            "two_handed": two_handed,
            "members": members,
            "tradeable": tradeable,
            "weight": weight,
            "game_id": game_id,
            "examine": examine,
            "attack_stab": parse_int(parse_versioned_param(bonuses_block, "astab", v)),
            "attack_slash": parse_int(parse_versioned_param(bonuses_block, "aslash", v)),
            "attack_crush": parse_int(parse_versioned_param(bonuses_block, "acrush", v)),
            "attack_magic": parse_int(parse_versioned_param(bonuses_block, "amagic", v)),
            "attack_ranged": parse_int(parse_versioned_param(bonuses_block, "arange", v)),
            "defence_stab": parse_int(parse_versioned_param(bonuses_block, "dstab", v)),
            "defence_slash": parse_int(parse_versioned_param(bonuses_block, "dslash", v)),
            "defence_crush": parse_int(parse_versioned_param(bonuses_block, "dcrush", v)),
            "defence_magic": parse_int(parse_versioned_param(bonuses_block, "dmagic", v)),
            "defence_ranged": parse_int(parse_versioned_param(bonuses_block, "drange", v)),
            "melee_strength": parse_int(parse_versioned_param(bonuses_block, "str", v)),
            "ranged_strength": parse_int(parse_versioned_param(bonuses_block, "rstr", v)),
            "magic_damage": parse_int(parse_versioned_param(bonuses_block, "mdmg", v)),
            "prayer": parse_int(parse_versioned_param(bonuses_block, "prayer", v)),
            "speed": parse_int(parse_versioned_param(bonuses_block, "speed", v)),
            "attack_range": parse_int(parse_versioned_param(bonuses_block, "attackrange", v)),
            "combat_style": parse_combat_style(parse_versioned_param(bonuses_block, "combatstyle", v)),
        }

        items.append(equipment)

    return items


EQUIPMENT_COLUMNS = [
    "name", "version", "item_id", "slot", "two_handed", "members", "tradeable", "weight",
    "game_id", "examine",
    "attack_stab", "attack_slash", "attack_crush", "attack_magic", "attack_ranged",
    "defence_stab", "defence_slash", "defence_crush", "defence_magic", "defence_ranged",
    "melee_strength", "ranged_strength", "magic_damage", "prayer",
    "speed", "attack_range", "combat_style",
]


SLOT_CATEGORIES = [
    "Weapon slot items",
    "Two-handed slot items",
    "Head slot items",
    "Body slot items",
    "Legs slot items",
    "Shield slot items",
    "Cape slot items",
    "Hands slot items",
    "Feet slot items",
    "Neck slot items",
    "Ring slot items",
    "Ammunition slot items",
]


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    # Collect pages from all slot categories (deduplicated)
    seen: set[str] = set()
    pages: list[str] = []
    for category in SLOT_CATEGORIES:
        members = fetch_category_members(category)
        for page in members:
            if page not in seen:
                seen.add(page)
                pages.append(page)
        print(f"  {category}: {len(members)} pages")
    print(f"Found {len(pages)} unique equipment pages across {len(SLOT_CATEGORIES)} slot categories")

    # Build item name → id lookup
    item_rows = conn.execute("SELECT id, name FROM items").fetchall()
    item_lookup: dict[str, int] = {name: id for id, name in item_rows}

    equipment_count = 0

    # Fetch wikitext in batches of 50
    all_wikitext: dict[str, str] = {}
    for i in range(0, len(pages), 50):
        batch = pages[i:i + 50]
        print(f"  Fetching pages {i + 1}-{i + len(batch)}...")
        all_wikitext.update(fetch_pages_wikitext_batch(batch))

    print(f"Fetched {len(all_wikitext)} pages, parsing...")

    for page_name, wikitext in all_wikitext.items():
        items = parse_equipment(page_name, wikitext)

        for equipment in items:
            # Resolve item_id from items table
            equipment["item_id"] = item_lookup.get(equipment["name"])

            placeholders = ", ".join("?" * len(EQUIPMENT_COLUMNS))
            cols = ", ".join(EQUIPMENT_COLUMNS)
            values = [equipment[c] for c in EQUIPMENT_COLUMNS]

            try:
                conn.execute(
                    f"INSERT OR IGNORE INTO equipment ({cols}) VALUES ({placeholders})",
                    values,
                )
                equipment_count += 1
            except OverflowError:
                print(f"  Skipping {equipment['name']} (version={equipment['version']}): integer overflow")
                continue

    conn.commit()
    print(f"Inserted {equipment_count} equipment entries")

    # Record attributions
    record_attributions_batch(conn, "equipment", list(all_wikitext.keys()))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch equipment data from the OSRS wiki")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
