"""Fetch farming actions from the OSRS wiki and populate the action tables.

Parses {{Farming info}} templates from pages that transclude them. Each crop
produces up to three actions — plant, check health, and harvest — depending
on which XP types exist for that crop.

Plant actions consume seed(s) as input items. Harvest actions produce crop(s)
as output items. All actions use the patch type as the ``at`` field. Growth
time and payment info are stored in notes.

No versioned templates — the wiki template does not support switch infobox.
Modelled as instant actions — ticks is NULL (farming is asynchronous).

Requires: fetch_items.py to have been run first (for item_id cross-referencing).
"""

import argparse
import re
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.enums import Skill
from ragger.wiki import (
    add_group_requirement,
    clean_name,
    create_requirement_group,
    extract_all_templates,
    fetch_pages_wikitext_batch,
    fetch_template_users,
    link_requirement_group,
    parse_int,
    parse_members,
    parse_template_param,
    parse_xp,
    record_attributions_batch,
    strip_plinks,
    strip_wiki_links,
    throttle,
)

_REF_TAG = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>|\{\{Refn\|[^}]*\}\}", re.DOTALL)
_YIELD_NUM = re.compile(r"(\d+)")


def _strip_refs(val: str | None) -> str | None:
    """Strip <ref> tags and {{Refn}} templates from a value."""
    if not val:
        return val
    return _REF_TAG.sub("", val).strip()


def _is_no(val: str | None) -> bool:
    """Check if a value means 'not applicable'."""
    if not val:
        return True
    return val.strip().lower() in ("no", "none", "n/a", "0", "")


def _parse_yield(val: str | None) -> int:
    """Parse yield field. Returns first number found, or 1 as default."""
    if not val or _is_no(val):
        return 1
    m = _YIELD_NUM.search(val.strip())
    return int(m.group(1)) if m else 1


def _parse_crop_items(crop_str: str, page_name: str) -> list[str]:
    """Parse crop field into list of item names.

    Handles comma-separated items like '{{plink|Magic logs}}, {{plink|Magic roots}}'.
    """
    items = []
    for part in re.split(r",\s*", crop_str):
        name = clean_name(part.strip(), page_name)
        if name:
            items.append(name)
    return items


def _parse_patch_type(patch_str: str | None) -> str | None:
    """Extract patch type from wiki-linked patch param."""
    if not patch_str:
        return None
    return strip_wiki_links(patch_str).strip() or None


def parse_farming_actions(block: str, page_name: str) -> list[dict]:
    """Parse a {{Farming info}} block into up to three action dicts.

    Returns plant, check-health, and/or harvest actions depending on which
    XP types are present for the crop.
    """
    name_raw = parse_template_param(block, "name")
    crop_name = clean_name(name_raw, page_name) if name_raw else page_name
    if not crop_name:
        return []

    members = parse_members(parse_template_param(block, "members"))
    level = parse_int(parse_template_param(block, "level"))
    if level is None:
        return []

    patch_type = _parse_patch_type(parse_template_param(block, "patch"))
    time_str = parse_template_param(block, "time")
    growth_time = strip_wiki_links(time_str).strip() if time_str else None

    # Payment
    payment_raw = parse_template_param(block, "payment")
    payment = None
    if payment_raw and not _is_no(payment_raw):
        payment = strip_plinks(strip_wiki_links(payment_raw)).strip()

    # Seed info
    seed_raw = parse_template_param(block, "seed")
    seed_name = clean_name(seed_raw, page_name) if seed_raw else None
    seedsper = parse_int(parse_template_param(block, "seedsper")) or 1

    # XP values (strip ref tags before parsing)
    plantxp = parse_xp(_strip_refs(parse_template_param(block, "plantxp")))
    checkxp_raw = _strip_refs(parse_template_param(block, "checkxp"))
    harvestxp_raw = _strip_refs(parse_template_param(block, "harvestxp"))

    has_check = not _is_no(checkxp_raw)
    has_harvest = not _is_no(harvestxp_raw)
    checkxp = parse_xp(checkxp_raw) if has_check else 0.0
    harvestxp = parse_xp(harvestxp_raw) if has_harvest else 0.0

    # Crop items (for harvest action output)
    crop_raw = parse_template_param(block, "crop")
    crop_items = _parse_crop_items(crop_raw, page_name) if crop_raw and not _is_no(crop_raw) else []
    harvest_yield = _parse_yield(parse_template_param(block, "yield"))

    actions = []

    # --- Plant action ---
    if plantxp > 0:
        notes_parts = ["Plant"]
        if growth_time:
            notes_parts.append(growth_time)
        if payment:
            notes_parts.append(f"Payment: {payment}")

        actions.append({
            "name": f"{crop_name} (Plant)",
            "page": page_name,
            "members": members,
            "ticks": None,
            "notes": " — ".join(notes_parts),
            "at": patch_type,
            "level": level,
            "xp": plantxp,
            "seed_name": seed_name,
            "seedsper": seedsper,
            "action_type": "plant",
        })

    # --- Check health action ---
    if has_check and checkxp > 0:
        actions.append({
            "name": f"{crop_name} (Check health)",
            "page": page_name,
            "members": members,
            "ticks": None,
            "notes": "Check health",
            "at": patch_type,
            "level": level,
            "xp": checkxp,
            "seed_name": None,
            "seedsper": 0,
            "action_type": "check",
        })

    # --- Harvest action ---
    if has_harvest and harvestxp > 0:
        actions.append({
            "name": f"{crop_name} (Harvest)",
            "page": page_name,
            "members": members,
            "ticks": None,
            "notes": "Harvest",
            "at": patch_type,
            "level": level,
            "xp": harvestxp,
            "seed_name": None,
            "seedsper": 0,
            "action_type": "harvest",
            "crop_items": crop_items,
            "crop_yield": harvest_yield,
        })

    return actions


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    # Find all pages that transclude Template:Farming info
    print("Finding pages with {{Farming info}}...")
    pages = fetch_template_users("Farming info")
    print(f"Found {len(pages)} pages")

    # Build item name -> id lookup
    item_rows = conn.execute("SELECT id, name FROM items").fetchall()
    item_lookup: dict[str, int] = {name: id for id, name in item_rows}

    def resolve_item(name: str) -> int | None:
        return item_lookup.get(name)

    # Clear existing farming actions for clean re-import
    old_ids = [r[0] for r in conn.execute(
        "SELECT action_id FROM source_actions WHERE source = 'farming'"
    ).fetchall()]
    if old_ids:
        placeholders = ",".join("?" * len(old_ids))
        for table in (
            "action_requirement_groups", "action_output_objects", "action_output_items",
            "action_output_experience", "action_input_currencies", "action_input_objects",
            "action_input_items",
        ):
            conn.execute(f"DELETE FROM {table} WHERE action_id IN ({placeholders})", old_ids)
        conn.execute("DELETE FROM source_actions WHERE source = 'farming'")
        conn.execute(f"DELETE FROM actions WHERE id IN ({placeholders})", old_ids)
    conn.commit()

    # Fetch wikitext in batches of 50
    all_wikitext: dict[str, str] = {}
    for i in range(0, len(pages), 50):
        batch = pages[i:i + 50]
        print(f"  Fetching pages {i + 1}-{i + len(batch)} of {len(pages)}...")
        all_wikitext.update(fetch_pages_wikitext_batch(batch))

    print(f"Fetched {len(all_wikitext)} pages, parsing...")

    # Parse all actions
    all_actions: list[dict] = []
    for page_name, wikitext in all_wikitext.items():
        blocks = extract_all_templates(wikitext, "Farming info")
        for block in blocks:
            all_actions.extend(parse_farming_actions(block, page_name))

    # Dedup by name — seed pages transclude plant pages
    seen: dict[str, dict] = {}
    for action in all_actions:
        key = action["name"]
        if key not in seen:
            seen[key] = action

    deduped_actions = list(seen.values())
    print(f"Parsed {len(all_actions)} raw, {len(deduped_actions)} after dedup")

    action_count = 0
    unresolved_seeds: set[str] = set()
    unresolved_crops: set[str] = set()

    for action in deduped_actions:
        cursor = conn.execute(
            "INSERT INTO actions (name, members, ticks, notes, at) VALUES (?, ?, ?, ?, ?)",
            (action["name"], action["members"], action["ticks"], action["notes"], action["at"]),
        )
        action_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO source_actions (source, action_id) VALUES ('farming', ?)",
            (action_id,),
        )

        # Farming level → requirement group
        group_id = create_requirement_group(conn)
        add_group_requirement(conn, group_id, "group_skill_requirements", {
            "skill": Skill.FARMING.value,
            "level": action["level"],
            "boostable": 0,
        })
        link_requirement_group(
            conn, "action_requirement_groups", "action_id", action_id, group_id,
        )

        # Farming XP → output experience
        if action["xp"] > 0:
            conn.execute(
                "INSERT OR IGNORE INTO action_output_experience (action_id, skill, xp) VALUES (?, ?, ?)",
                (action_id, Skill.FARMING.value, action["xp"]),
            )

        # Seed → input item (plant actions only)
        if action["seed_name"] and action["seedsper"] > 0:
            seed_item_id = resolve_item(action["seed_name"])
            if seed_item_id is not None:
                conn.execute(
                    "INSERT INTO action_input_items (action_id, item_id, item_name, quantity) VALUES (?, ?, ?, ?)",
                    (action_id, seed_item_id, action["seed_name"], action["seedsper"]),
                )
            else:
                unresolved_seeds.add(action["seed_name"])

        # Crop → output items (harvest actions only)
        crop_items = action.get("crop_items", [])
        crop_yield = action.get("crop_yield", 1)
        for crop_name in crop_items:
            crop_item_id = resolve_item(crop_name)
            if crop_item_id is not None:
                conn.execute(
                    "INSERT INTO action_output_items (action_id, item_id, item_name, quantity) VALUES (?, ?, ?, ?)",
                    (action_id, crop_item_id, crop_name, crop_yield),
                )
            else:
                unresolved_crops.add(crop_name)

        action_count += 1

    conn.commit()
    print(f"Inserted {action_count} farming actions")
    if unresolved_seeds:
        print(f"  Unresolved seeds ({len(unresolved_seeds)}): {sorted(unresolved_seeds)}")
    if unresolved_crops:
        print(f"  Unresolved crops ({len(unresolved_crops)}): {sorted(unresolved_crops)}")

    # Record attributions
    table_names = ["actions", "action_output_experience", "action_input_items", "action_output_items"]
    record_attributions_batch(conn, table_names, list(all_wikitext.keys()))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch farming actions from the OSRS wiki")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
