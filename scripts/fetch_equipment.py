"""Fetch equipment data from the OSRS wiki and populate the equipment table.

Parses {{Infobox Bonuses}} for combat stats and {{Infobox Item}} for metadata.
Extracts skill and quest requirements from article prose.
Uses batched API calls for efficiency.

Requires: fetch_items.py and fetch_quests.py to have been run first.
"""

import argparse
import re
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.enums import CombatStyle, EquipmentSlot, Skill
from ragger.wiki import (
    SKILL_NAME_MAP,
    WIKI_LINK_PATTERN,
    extract_template,
    fetch_category_members,
    fetch_pages_wikitext_batch,
    link_group_requirement,
    parse_int,
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


# Matches "N [[Skill]]" — a level followed by a wiki-linked skill name
_LEVEL_SKILL_PATTERN = re.compile(r"(\d{1,2})\s*\[\[(\w[\w ]*?)\]\]")
# Matches "[[Skill]] level of N"
_SKILL_LEVEL_OF_PATTERN = re.compile(r"\[\[(\w[\w ]*?)\]\]\s*level of\s*(\d{1,2})")
# Matches quest links following "completion of" or "completed"
_QUEST_COMPLETION_PATTERN = re.compile(
    r"complet(?:ion of|ed?)\s+(?:the\s+)?(?:\[\[quest\]\]\s*)?\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]",
    re.IGNORECASE,
)


def _get_intro(wikitext: str) -> str:
    """Extract the intro text before the first == section heading ==."""
    match = re.search(r"^==\s*\w", wikitext, re.MULTILINE)
    return wikitext[:match.start()] if match else wikitext


def parse_equipment_requirements(
    wikitext: str,
) -> tuple[list[tuple[Skill, int]], list[str]]:
    """Parse skill and quest requirements from equipment page prose.

    Returns (skill_reqs, quest_reqs) where skill_reqs is [(Skill, level), ...]
    and quest_reqs is [quest_name, ...].
    """
    intro = _get_intro(wikitext)

    # --- Skill requirements ---
    skill_reqs: list[tuple[Skill, int]] = []
    seen_skills: set[Skill] = set()

    # Pattern 1: "N [[Skill]]" — also handles "N [[Skill1]] and [[Skill2]]"
    # where the second skill inherits the level from the first.
    for match in _LEVEL_SKILL_PATTERN.finditer(intro):
        level = int(match.group(1))
        skill_name = match.group(2).strip().lower()
        skill = SKILL_NAME_MAP.get(skill_name)
        if skill is not None and skill not in seen_skills and 1 <= level <= 99:
            skill_reqs.append((skill, level))
            seen_skills.add(skill)

            # Check for additional skills sharing the same level:
            # "requires 70 [[Defence]] and [[Ranged]] to wear"
            rest = intro[match.end():]
            for follow in re.finditer(r"(?:,\s*|\s+and\s+)\[\[(\w[\w ]*?)\]\]", rest):
                follow_skill = SKILL_NAME_MAP.get(follow.group(1).strip().lower())
                if follow_skill is not None and follow_skill not in seen_skills:
                    skill_reqs.append((follow_skill, level))
                    seen_skills.add(follow_skill)
                else:
                    break  # hit a non-skill link, stop chaining

    # Pattern 2: "[[Skill]] level of N"
    for match in _SKILL_LEVEL_OF_PATTERN.finditer(intro):
        skill_name = match.group(1).strip().lower()
        level = int(match.group(2))
        skill = SKILL_NAME_MAP.get(skill_name)
        if skill is not None and skill not in seen_skills and 1 <= level <= 99:
            skill_reqs.append((skill, level))
            seen_skills.add(skill)

    # --- Quest requirements ---
    quest_reqs: list[str] = []

    # From Infobox Item |quest= parameter (e.g. |quest = [[Roving Elves]])
    item_block = extract_template(wikitext, "Infobox Item")
    if item_block:
        quest_val = parse_template_param(item_block, "quest")
        if quest_val:
            for link_match in WIKI_LINK_PATTERN.finditer(quest_val):
                quest_name = link_match.group(1).strip()
                if quest_name.lower() not in ("no", "yes", "quest"):
                    quest_reqs.append(quest_name)

    # From prose: "completion of [[Quest]]" / "completed [[Quest]]"
    for match in _QUEST_COMPLETION_PATTERN.finditer(intro):
        quest_name = match.group(1).strip()
        if quest_name not in quest_reqs:
            quest_reqs.append(quest_name)

    return skill_reqs, quest_reqs


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

        slot_val, two_handed = parse_slot(parse_versioned_param(bonuses_block, "slot", v))

        equipment = {
            "name": item_name,
            "version": version_label,
            "slot": slot_val,
            "two_handed": two_handed,
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
    "name", "version", "item_id", "slot", "two_handed",
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

    # Build equipment (name, version) → id lookup
    equip_rows = conn.execute("SELECT id, name, version FROM equipment").fetchall()
    equip_lookup: dict[tuple[str, str | None], int] = {
        (name, version): eid for eid, name, version in equip_rows
    }

    # Build quest name → id lookup
    quest_ids: dict[str, int] = dict(
        conn.execute("SELECT name, id FROM quests").fetchall()
    )

    # Link requirements
    skill_req_count = 0
    quest_req_count = 0
    for page_name, wikitext in all_wikitext.items():
        skill_reqs, quest_reqs = parse_equipment_requirements(wikitext)
        if not skill_reqs and not quest_reqs:
            continue

        # Find all equipment entries from this page
        items = parse_equipment(page_name, wikitext)
        for equipment in items:
            equip_id = equip_lookup.get((equipment["name"], equipment["version"]))
            if equip_id is None:
                continue

            for skill, level in skill_reqs:
                link_group_requirement(
                    conn,
                    "group_skill_requirements",
                    {"skill": skill.value, "level": level},
                    "equipment_requirement_groups",
                    "equipment_id",
                    equip_id,
                )
                skill_req_count += 1

            for quest_name in quest_reqs:
                quest_id = quest_ids.get(quest_name)
                if quest_id is None:
                    continue
                link_group_requirement(
                    conn,
                    "group_quest_requirements",
                    {"required_quest_id": quest_id},
                    "equipment_requirement_groups",
                    "equipment_id",
                    equip_id,
                )
                quest_req_count += 1

    conn.commit()
    print(f"Linked {skill_req_count} skill requirements, {quest_req_count} quest requirements")

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
