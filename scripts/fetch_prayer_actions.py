"""Fetch prayer actions from the OSRS wiki and populate the action tables.

Parses {{Prayer info}} templates from pages that transclude them. Each entry
represents a Prayer XP source — bones, ashes, fossils, reanimated creatures,
spectral monsters, or miscellaneous items.

Bones produce up to four actions depending on which methods are available:
bury (1x), altar (3.5x), ectofuntus (4x), sinister offering (3x). Ashes
produce scatter (1x) and demonic offering (3x). Other types produce a single
action with the base XP.

Input items are the bones/ashes themselves. Prayer XP is the output. The
offering method is stored in the ``at`` field, type in notes.

Modelled as instant actions — ticks is NULL.

Requires: fetch_items.py to have been run first (for item_id cross-referencing).
"""

import argparse
import html
import re
from pathlib import Path

from ragger.action import Action
from ragger.db import create_tables, get_connection
from ragger.enums import Skill, TriggerType
from ragger.wiki import (
    WIKI_BATCH_SIZE,
    add_group_requirement,
    clean_name,
    create_requirement_group,
    detect_versions,
    extract_all_templates,
    fetch_pages_wikitext_batch,
    fetch_template_users,
    link_requirement_group,
    parse_int,
    parse_members,
    parse_template_param,
    parse_xp,
    record_attributions_batch,
    strip_refs,
    throttle,
)

# Key used in source_actions to identify rows belonging to this script.
_SOURCE = "wiki-prayer"
# Wiki template name whose transclusions are fetched and parsed.
_TEMPLATE = "Prayer info"

_BR_TAG = re.compile(r"\s*<br\s*/?\s*>.*", re.DOTALL | re.IGNORECASE)


def _clean_prayer_name(val: str | None, page_name: str) -> str | None:
    """Clean a prayer name field — decode HTML entities and strip <br> markup."""
    if not val:
        return None
    val = html.unescape(val)
    val = _BR_TAG.sub("", val)
    return clean_name(val, page_name) or None


def _is_no(val: str | None) -> bool:
    """Check if a parameter is explicitly set to 'no'."""
    if not val:
        return False
    return val.strip().lower() == "no"


# XP multipliers for bone offering methods
_BONE_METHODS = [
    # (suffix, multiplier, flag_to_check, trigger_types)
    ("Bury", 1.0, "burying", TriggerType.CLICK_ITEM.mask),
    ("Altar", 3.5, "altar", TriggerType.USE_ITEM_ON_OBJECT.mask),
    ("Ectofuntus", 4.0, "ectofuntus", TriggerType.USE_ITEM_ON_OBJECT.mask),
    ("Sinister Offering", 3.0, "sinister", TriggerType.CLICK_WIDGET.mask),
]

_ASH_METHODS = [
    # (suffix, multiplier, flag_to_check, trigger_types)
    ("Scatter", 1.0, None, TriggerType.CLICK_ITEM.mask),
    ("Demonic Offering", 3.0, None, TriggerType.CLICK_WIDGET.mask),
]


def parse_prayer_actions(block: str, page_name: str) -> list[dict]:
    """Parse a {{Prayer info}} block into one or more action dicts.

    Versioned templates produce one set of actions per version. Each type
    generates a different set of offering method actions.
    """
    versions = detect_versions(block)

    if not versions:
        return _parse_single_version(block, page_name, suffix="")

    actions = []
    for vi, version_name in enumerate(versions, 1):
        suffix = str(vi)
        version_actions = _parse_single_version(block, page_name, suffix=suffix)
        for action in version_actions:
            # Append version name if not already in the action name
            base = action["name"]
            # Replace the method suffix to include version
            # e.g. "Bones (Bury)" with version "Regular" -> "Bones (Regular, Bury)"
            m = re.match(r"^(.+?) \(([^)]+)\)$", base)
            if m:
                action["name"] = f"{m.group(1)} ({version_name}, {m.group(2)})"
            else:
                action["name"] = f"{base} ({version_name})"
        actions.extend(version_actions)
    return actions


def _parse_single_version(
    block: str, page_name: str, suffix: str,
) -> list[dict]:
    """Parse one version of a Prayer info block into actions."""
    name_raw = parse_template_param(block, f"name{suffix}")
    if name_raw is None:
        name_raw = parse_template_param(block, "name")
    target_name = _clean_prayer_name(name_raw, page_name) if name_raw else page_name
    if not target_name:
        return []

    members = parse_members(parse_template_param(block, f"members{suffix}"))
    if members is None:
        members = parse_members(parse_template_param(block, "members"))

    level_str = parse_template_param(block, f"level{suffix}")
    if level_str is None:
        level_str = parse_template_param(block, "level")
    level = parse_int(level_str)
    if level is None:
        return []

    xp_str = strip_refs(parse_template_param(block, f"xp{suffix}"))
    if xp_str is None:
        xp_str = strip_refs(parse_template_param(block, "xp"))
    base_xp = parse_xp(xp_str)
    if base_xp <= 0:
        return []

    type_raw = parse_template_param(block, f"type{suffix}")
    if type_raw is None:
        type_raw = parse_template_param(block, "type")
    prayer_type = type_raw.strip().lower() if type_raw else "other"

    actions = []

    if prayer_type == "bone":
        for method_name, multiplier, flag, trigger in _BONE_METHODS:
            if flag and _is_no(parse_template_param(block, flag)):
                continue
            xp = round(base_xp * multiplier, 1)
            actions.append({
                "name": f"{target_name} ({method_name})",
                "item_name": target_name,
                "page": page_name,
                "members": members,
                "ticks": None,
                "notes": f"bone — {method_name}",
                "trigger_types": trigger,
                "level": level,
                "xp": xp,
            })

    elif prayer_type == "ashes":
        for method_name, multiplier, _flag, trigger in _ASH_METHODS:
            xp = round(base_xp * multiplier, 1)
            actions.append({
                "name": f"{target_name} ({method_name})",
                "item_name": target_name,
                "page": page_name,
                "members": members,
                "ticks": None,
                "notes": f"ashes — {method_name}",
                "trigger_types": trigger,
                "level": level,
                "xp": xp,
            })

    elif prayer_type == "bonemeal":
        actions.append({
            "name": target_name,
            "item_name": target_name,
            "page": page_name,
            "members": members,
            "ticks": None,
            "notes": "bonemeal",
            "trigger_types": TriggerType.USE_ITEM_ON_OBJECT.mask,
            "level": level,
            "xp": base_xp,
        })

    elif prayer_type == "reanimated":
        actions.append({
            "name": target_name,
            "item_name": None,
            "page": page_name,
            "members": members,
            "ticks": None,
            "notes": "reanimated",
            "trigger_types": TriggerType.CLICK_WIDGET.mask,
            "level": level,
            "xp": base_xp,
        })

    elif prayer_type == "spectral":
        actions.append({
            "name": target_name,
            "item_name": None,
            "page": page_name,
            "members": members,
            "ticks": None,
            "notes": "spectral — Ectoplasmator",
            "trigger_types": 0,
            "level": level,
            "xp": base_xp,
        })

    elif prayer_type == "fossil":
        actions.append({
            "name": target_name,
            "item_name": target_name,
            "page": page_name,
            "members": members,
            "ticks": None,
            "notes": "fossil",
            "trigger_types": TriggerType.USE_ITEM_ON_OBJECT.mask,
            "level": level,
            "xp": base_xp,
        })

    else:  # "other"
        actions.append({
            "name": target_name,
            "item_name": target_name,
            "page": page_name,
            "members": members,
            "ticks": None,
            "notes": prayer_type,
            "trigger_types": 0,
            "level": level,
            "xp": base_xp,
        })

    return actions


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    # Find all pages that transclude Template:Prayer info
    print(f"Finding pages with {{{{{_TEMPLATE}}}}}...")
    pages = fetch_template_users(_TEMPLATE)
    print(f"Found {len(pages)} pages")

    # Build item name -> id lookup
    item_rows = conn.execute("SELECT id, name FROM items").fetchall()
    item_lookup: dict[str, int] = {name: id for id, name in item_rows}

    def resolve_item(name: str) -> int | None:
        return item_lookup.get(name)

    Action.delete_by_source(conn, _SOURCE)
    conn.commit()

    # Fetch wikitext in batches of 50
    all_wikitext: dict[str, str] = {}
    for i in range(0, len(pages), WIKI_BATCH_SIZE):
        batch = pages[i:i + WIKI_BATCH_SIZE]
        print(f"  Fetching pages {i + 1}-{i + len(batch)} of {len(pages)}...")
        all_wikitext.update(fetch_pages_wikitext_batch(batch))

    print(f"Fetched {len(all_wikitext)} pages, parsing...")

    # Parse all actions
    all_actions: list[dict] = []
    for page_name, wikitext in all_wikitext.items():
        blocks = extract_all_templates(wikitext, _TEMPLATE)
        for block in blocks:
            all_actions.extend(parse_prayer_actions(block, page_name))

    # Dedup by name
    seen: dict[str, dict] = {}
    for action in all_actions:
        key = action["name"]
        if key not in seen:
            seen[key] = action

    deduped_actions = list(seen.values())
    print(f"Parsed {len(all_actions)} raw, {len(deduped_actions)} after dedup")

    action_count = 0
    unresolved_items: set[str] = set()

    for action in deduped_actions:
        cursor = conn.execute(
            "INSERT INTO actions (name, members, ticks, notes, trigger_types) VALUES (?, ?, ?, ?, ?)",
            (action["name"], action["members"], action["ticks"], action["notes"], action["trigger_types"]),
        )
        action_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO source_actions (source, action_id) VALUES (?, ?)",
            (_SOURCE, action_id),
        )

        # Prayer level → requirement group
        group_id = create_requirement_group(conn)
        add_group_requirement(conn, group_id, "group_skill_requirements", {
            "skill": Skill.PRAYER.value,
            "level": action["level"],
            "boostable": 0,
        })
        link_requirement_group(
            conn, "action_requirement_groups", "action_id", action_id, group_id,
        )

        # Prayer XP → output experience
        if action["xp"] > 0:
            conn.execute(
                "INSERT OR IGNORE INTO action_output_experience (action_id, skill, xp) VALUES (?, ?, ?)",
                (action_id, Skill.PRAYER.value, action["xp"]),
            )

        # Item → input item (bones/ashes consumed)
        item_name = action.get("item_name")
        if item_name:
            item_id = resolve_item(item_name)
            if item_id is not None:
                conn.execute(
                    "INSERT INTO action_input_items (action_id, item_id, item_name, quantity) VALUES (?, ?, ?, ?)",
                    (action_id, item_id, item_name, 1),
                )
            else:
                unresolved_items.add(item_name)

        action_count += 1

    conn.commit()
    print(f"Inserted {action_count} prayer actions")
    if unresolved_items:
        print(f"  Unresolved items ({len(unresolved_items)}): {sorted(unresolved_items)}")

    # Record attributions
    table_names = ["actions", "action_output_experience", "action_input_items"]
    record_attributions_batch(conn, table_names, list(all_wikitext.keys()))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch prayer actions from the OSRS wiki")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
