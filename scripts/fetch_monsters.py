"""Fetch monster data from the OSRS wiki and populate monsters/monster_locations/monster_drops tables.

Parses {{Infobox Monster}}, {{LocLine}}, and {{DropsLine}} templates.
Uses batched API calls for efficiency.

Requires: fetch_items.py to have been run first (for drop cross-referencing).
"""

import argparse
import re
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.enums import Immunity, Skill
from ragger.wiki import (
    WIKI_LINK_PATTERN,
    extract_coords,
    extract_template,
    fetch_category_members,
    fetch_pages_wikitext_batch,
    link_group_requirement,
    parse_template_param,
    record_attributions_batch,
    resolve_region,
    strip_wiki_links,
)
DROPS_LINE_PATTERN = re.compile(r"\{\{DropsLine([^}]*)\}\}")

# Matches quest links following "completion of" or "completed"
_QUEST_COMPLETION_PATTERN = re.compile(
    r"complet(?:ion of|ed?)\s+(?:the\s+)?(?:\[\[quest\]\]\s*)?\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]",
    re.IGNORECASE,
)


def _get_intro(wikitext: str) -> str:
    """Extract the intro text before the first == section heading ==."""
    match = re.search(r"^==\s*\w", wikitext, re.MULTILINE)
    return wikitext[:match.start()] if match else wikitext


def parse_monster_requirements(
    wikitext: str,
) -> tuple[int | None, list[str]]:
    """Parse slayer level and quest requirements from monster page.

    Returns (slayer_level, quest_names) where slayer_level comes from the
    Infobox Monster |slaylvl= param and quest_names from prose patterns.
    """
    # --- Slayer level from template ---
    slayer_level = None
    block = extract_template(wikitext, "Infobox Monster")
    if block:
        slaylvl = parse_template_param(block, "slaylvl")
        if slaylvl:
            slaylvl = slaylvl.strip().replace(",", "")
            try:
                slayer_level = int(slaylvl)
                if slayer_level < 1 or slayer_level > 99:
                    slayer_level = None
            except ValueError:
                slayer_level = None

    # --- Quest requirements from prose ---
    intro = _get_intro(wikitext)
    quest_reqs: list[str] = []
    for match in _QUEST_COMPLETION_PATTERN.finditer(intro):
        quest_name = match.group(1).strip()
        if quest_name not in quest_reqs:
            quest_reqs.append(quest_name)

    return slayer_level, quest_reqs


def parse_versioned_param(block: str, param: str, version: str) -> str | None:
    """Try versioned param first (e.g. hitpoints1), then unversioned."""
    val = parse_template_param(block, f"{param}{version}")
    if val is None:
        val = parse_template_param(block, param)
    return val


def parse_int(val: str | None) -> int | None:
    if not val:
        return None
    val = val.strip().replace(",", "")
    try:
        return int(val)
    except ValueError:
        return None


def parse_float(val: str | None) -> float | None:
    if not val:
        return None
    val = val.strip().replace(",", "")
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


def parse_immunities(block: str, version: str) -> int:
    """Parse immunity fields into a bitmask."""
    mask = 0
    mapping = {
        "immunepoison": Immunity.POISON,
        "immunevenom": Immunity.VENOM,
        "immunecannon": Immunity.CANNON,
        "immunethrall": Immunity.THRALL,
        "immuneburn": Immunity.BURN,
    }
    for param, immunity in mapping.items():
        val = parse_versioned_param(block, param, version)
        if val and "immune" in val.lower() and "not immune" not in val.lower():
            mask |= immunity.mask
    return mask


def get_versions(block: str) -> list[str]:
    """Detect how many versions a monster has."""
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


def parse_monster(name: str, wikitext: str) -> list[dict]:
    """Parse all monster versions from a page's wikitext."""
    block = extract_template(wikitext, "Infobox Monster")
    if not block:
        return []

    versions = get_versions(block)
    monsters = []

    for v in versions:
        version_label = parse_template_param(block, f"version{v}") if v else None

        monster = {
            "name": name,
            "version": version_label,
            "combat_level": parse_int(parse_versioned_param(block, "combat", v)),
            "hitpoints": parse_int(parse_versioned_param(block, "hitpoints", v)),
            "attack_speed": parse_int(parse_versioned_param(block, "attack speed", v)),
            "max_hit": parse_versioned_param(block, "max hit", v),
            "attack_style": parse_versioned_param(block, "attack style", v),
            "aggressive": parse_bool(parse_versioned_param(block, "aggressive", v)),
            "size": parse_int(parse_versioned_param(block, "size", v)),
            "respawn": parse_int(parse_versioned_param(block, "respawn", v)),
            "attack_level": parse_int(parse_versioned_param(block, "att", v)),
            "strength_level": parse_int(parse_versioned_param(block, "str", v)),
            "defence_level": parse_int(parse_versioned_param(block, "def", v)),
            "magic_level": parse_int(parse_versioned_param(block, "mage", v)),
            "ranged_level": parse_int(parse_versioned_param(block, "range", v)),
            "attack_bonus": parse_int(parse_versioned_param(block, "attbns", v)),
            "strength_bonus": parse_int(parse_versioned_param(block, "strbns", v)),
            "magic_attack": parse_int(parse_versioned_param(block, "amagic", v)),
            "magic_strength": parse_int(parse_versioned_param(block, "mbns", v)),
            "ranged_attack": parse_int(parse_versioned_param(block, "arange", v)),
            "ranged_strength": parse_int(parse_versioned_param(block, "rngbns", v)),
            "defensive_stab": parse_int(parse_versioned_param(block, "dstab", v)),
            "defensive_slash": parse_int(parse_versioned_param(block, "dslash", v)),
            "defensive_crush": parse_int(parse_versioned_param(block, "dcrush", v)),
            "defensive_magic": parse_int(parse_versioned_param(block, "dmagic", v)),
            "defensive_light_ranged": parse_int(parse_versioned_param(block, "dlight", v)),
            "defensive_standard_ranged": parse_int(parse_versioned_param(block, "dstandard", v)),
            "defensive_heavy_ranged": parse_int(parse_versioned_param(block, "dheavy", v)),
            "elemental_weakness_type": parse_versioned_param(block, "elementalweaknesstype", v),
            "elemental_weakness_percent": parse_int(parse_versioned_param(block, "elementalweaknesspercent", v)),
            "immunities": parse_immunities(block, v),
            "slayer_xp": parse_float(parse_versioned_param(block, "slayxp", v)),
            "slayer_category": parse_template_param(block, "cat"),
            "slayer_assigned_by": parse_template_param(block, "assignedby"),
            "attributes": parse_template_param(block, "attributes"),
            "examine": parse_versioned_param(block, "examine", v),
            "members": parse_bool(parse_template_param(block, "members")),
        }

        # Strip wiki markup from text fields
        for key in ("max_hit", "attack_style", "examine", "slayer_assigned_by"):
            if monster[key]:
                monster[key] = strip_wiki_links(monster[key])

        monsters.append(monster)

    return monsters


def parse_loc_lines(wikitext: str) -> list[dict]:
    """Parse {{LocLine}} templates for spawn locations."""
    locations = []
    i = 0
    while i < len(wikitext):
        if wikitext[i:i + 9] == "{{LocLine":
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
                        loc_name = parse_template_param(block, "location")
                        if loc_name:
                            loc_name = strip_wiki_links(loc_name)
                        region = resolve_region(parse_template_param(block, "leagueRegion"))
                        version = parse_template_param(block, "version")

                        for x, y in extract_coords(block):
                            locations.append({
                                "location": loc_name,
                                "x": x,
                                "y": y,
                                "region": region,
                                "version": version,
                            })
                        break
                else:
                    i += 1
        else:
            i += 1
    return locations


def parse_drops(wikitext: str) -> list[dict]:
    """Parse {{DropsLine}} templates for drop table entries."""
    drops = []
    for match in DROPS_LINE_PATTERN.finditer(wikitext):
        block = match.group(1)
        item_name = parse_template_param(block, "name")
        if not item_name:
            continue
        item_name = strip_wiki_links(item_name)
        drops.append({
            "item_name": item_name,
            "quantity": parse_template_param(block, "quantity"),
            "rarity": parse_template_param(block, "rarity"),
        })
    return drops


MONSTER_COLUMNS = [
    "name", "version", "combat_level", "hitpoints", "attack_speed", "max_hit",
    "attack_style", "aggressive", "size", "respawn",
    "attack_level", "strength_level", "defence_level", "magic_level", "ranged_level",
    "attack_bonus", "strength_bonus", "magic_attack", "magic_strength",
    "ranged_attack", "ranged_strength",
    "defensive_stab", "defensive_slash", "defensive_crush", "defensive_magic",
    "defensive_light_ranged", "defensive_standard_ranged", "defensive_heavy_ranged",
    "elemental_weakness_type", "elemental_weakness_percent", "immunities",
    "slayer_xp", "slayer_category", "slayer_assigned_by",
    "attributes", "examine", "members",
]


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    pages = fetch_category_members("Monsters")
    print(f"Found {len(pages)} pages in Category:Monsters")

    monster_count = 0
    location_count = 0
    drop_count = 0

    # Fetch wikitext in batches of 50
    all_wikitext: dict[str, str] = {}
    for i in range(0, len(pages), 50):
        batch = pages[i:i + 50]
        print(f"  Fetching pages {i + 1}-{i + len(batch)}...")
        all_wikitext.update(fetch_pages_wikitext_batch(batch))

    print(f"Fetched {len(all_wikitext)} pages, parsing...")

    for page_name, wikitext in all_wikitext.items():
        monsters = parse_monster(page_name, wikitext)
        loc_lines = parse_loc_lines(wikitext)
        drops = parse_drops(wikitext)

        for monster in monsters:
            placeholders = ", ".join("?" * len(MONSTER_COLUMNS))
            cols = ", ".join(MONSTER_COLUMNS)
            values = [monster[c] for c in MONSTER_COLUMNS]

            conn.execute(
                f"INSERT OR IGNORE INTO monsters ({cols}) VALUES ({placeholders})",
                values,
            )
            row = conn.execute(
                "SELECT id FROM monsters WHERE name = ? AND version IS ?",
                (monster["name"], monster["version"]),
            ).fetchone()
            if not row:
                continue
            monster_id = row[0]

            # Link locations matching this version
            for loc in loc_lines:
                if loc["version"] and monster["version"] and loc["version"] != monster["version"]:
                    continue
                conn.execute(
                    "INSERT INTO monster_locations (monster_id, location, x, y, region) VALUES (?, ?, ?, ?, ?)",
                    (monster_id, loc["location"], loc["x"], loc["y"], loc["region"]),
                )
                location_count += 1

            # Link drops (shared across versions unless specified otherwise)
            for drop in drops:
                conn.execute(
                    "INSERT INTO monster_drops (monster_id, item_name, quantity, rarity) VALUES (?, ?, ?, ?)",
                    (monster_id, drop["item_name"], drop["quantity"], drop["rarity"]),
                )
                drop_count += 1

            monster_count += 1

    conn.commit()
    print(f"Inserted {monster_count} monsters, {location_count} spawn locations, {drop_count} drop entries")

    # --- Link requirements ---
    # Build monster (name, version) → id lookup
    monster_rows = conn.execute("SELECT id, name, version FROM monsters").fetchall()
    monster_lookup: dict[tuple[str, str | None], int] = {
        (name, version): mid for mid, name, version in monster_rows
    }

    # Build quest name → id lookup
    quest_ids: dict[str, int] = dict(
        conn.execute("SELECT name, id FROM quests").fetchall()
    )

    skill_req_count = 0
    quest_req_count = 0

    for page_name, wikitext in all_wikitext.items():
        slayer_level, quest_reqs = parse_monster_requirements(wikitext)
        if slayer_level is None and not quest_reqs:
            continue

        monsters = parse_monster(page_name, wikitext)
        for monster in monsters:
            mid = monster_lookup.get((monster["name"], monster["version"]))
            if mid is None:
                continue

            if slayer_level is not None:
                link_group_requirement(
                    conn,
                    "group_skill_requirements",
                    {"skill": Skill.SLAYER.value, "level": slayer_level},
                    "monster_requirement_groups",
                    "monster_id",
                    mid,
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
                    "monster_requirement_groups",
                    "monster_id",
                    mid,
                )
                quest_req_count += 1

    conn.commit()
    print(f"Linked {skill_req_count} slayer requirements, {quest_req_count} quest requirements")

    print("Recording attributions...")
    record_attributions_batch(conn, ["monsters", "monster_locations", "monster_drops"], pages)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch OSRS monster data")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
