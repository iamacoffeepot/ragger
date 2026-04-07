"""Fetch hunter actions from the OSRS wiki and populate the action tables.

Parses {{Hunter info}} templates from pages that transclude them. Each
creature becomes one action (or one per version for Herbiboar-style pages).
Trap items become tool requirements, bait becomes input items, and the caught
creature maps to an output item. Modelled as instant catch — ticks is NULL.

Requires: fetch_items.py to have been run first (for item_id cross-referencing).
"""

import argparse
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
    throttle,
)

# Key used in source_actions to identify rows belonging to this script.
_SOURCE = "wiki-hunter"
# Wiki template name whose transclusions are fetched and parsed.
_TEMPLATE = "Hunter info"

# Matches range values like "1,950–2,461" or "25–75" — take the first number
_RANGE_DASH = re.compile(r"^([\d,.]+)\s*[–\-]\s*[\d,.]+$")


def _parse_range_xp(val: str | None) -> float:
    """Parse XP that may be a range (e.g. '1,950–2,461'). Takes the low end."""
    if not val:
        return 0.0
    m = _RANGE_DASH.match(val.strip())
    if m:
        return parse_xp(m.group(1))
    return parse_xp(val)


def parse_hunter_actions(block: str, page_name: str) -> list[dict]:
    """Parse a {{Hunter info}} block into one or more action dicts.

    Versioned templates (e.g. Herbiboar: Hunting vs Harvesting) produce
    one action per version. Unversioned produce a single action.
    """
    name_raw = parse_template_param(block, "name")
    if not name_raw:
        return []
    creature_name = clean_name(name_raw, page_name)
    if not creature_name:
        return []

    members = parse_members(parse_template_param(block, "members"))

    versions = detect_versions(block)

    if not versions:
        action = _parse_single_version(block, page_name, creature_name, members, suffix="")
        return [action] if action else []

    actions = []
    for vi, version_name in enumerate(versions, 1):
        suffix = str(vi)
        action = _parse_single_version(block, page_name, creature_name, members, suffix=suffix)
        if action:
            action["name"] = f"{creature_name} ({version_name})"
            action["notes"] = version_name
            actions.append(action)
    return actions


def _parse_single_version(
    block: str, page_name: str, creature_name: str, members: int, suffix: str,
) -> dict | None:
    """Parse one version of a Hunter info block."""
    action: dict = {
        "name": creature_name,
        "page": page_name,
        "members": members,
        "ticks": None,
        "notes": None,
        "trigger_types": TriggerType.CLICK_OBJECT.mask,
        "skills": [],
        "tools": [],
        "input_items": [],
    }

    # Parse skills — skill1 is always Hunter unless overridden by skill1name
    i = 1
    while True:
        if i == 1:
            skill_name_raw = parse_template_param(block, f"skill{i}name{suffix}")
            if not skill_name_raw:
                skill_name_raw = parse_template_param(block, f"skill{i}name")
            skill = Skill.HUNTER
            if skill_name_raw:
                try:
                    skill = Skill.from_label(skill_name_raw.strip())
                except KeyError:
                    pass
        else:
            skill_name_raw = parse_template_param(block, f"skill{i}name{suffix}")
            if not skill_name_raw:
                skill_name_raw = parse_template_param(block, f"skill{i}name")
            if not skill_name_raw:
                break
            try:
                skill = Skill.from_label(skill_name_raw.strip())
            except KeyError:
                i += 1
                continue

        # Level: versioned first, then unversioned, then shorthand
        level_str = parse_template_param(block, f"skill{i}lvl{suffix}")
        if level_str is None:
            level_str = parse_template_param(block, f"skill{i}lvl")
        if level_str is None and suffix:
            level_str = parse_template_param(block, f"level{suffix}")
        if level_str is None and i == 1:
            level_str = parse_template_param(block, "level")
        # Strip "(boostable)" suffix from level values like "80 (boostable)"
        if level_str:
            level_str = re.sub(r"\s*\(.*?\)\s*$", "", level_str)
        level = parse_int(level_str)
        if level is None:
            i += 1
            continue

        # XP: versioned first, then unversioned, then shorthand
        xp_str = parse_template_param(block, f"skill{i}exp{suffix}")
        if xp_str is None:
            xp_str = parse_template_param(block, f"skill{i}exp")
        if xp_str is None and suffix:
            xp_str = parse_template_param(block, f"xp{suffix}")
        if xp_str is None and i == 1:
            xp_str = parse_template_param(block, "xp")
        xp = _parse_range_xp(xp_str)

        action["skills"].append({
            "skill": skill.value,
            "level": level,
            "xp": xp,
        })
        i += 1

    if not action["skills"]:
        return None

    # Trap → tool requirement
    trap_str = parse_template_param(block, f"trap{suffix}")
    if trap_str is None:
        trap_str = parse_template_param(block, "trap")
    # Also check "tool" param (Herbiboar uses toolname/tool)
    tool_str = parse_template_param(block, f"tool{suffix}")
    if tool_str is None:
        tool_str = parse_template_param(block, "tool")

    for raw in (trap_str, tool_str):
        if raw and raw.strip().lower() not in ("no", "none", "n/a"):
            tool_name = clean_name(raw, page_name)
            if tool_name:
                action["tools"].append(tool_name)

    # Bait → input item
    bait_str = parse_template_param(block, f"bait{suffix}")
    if bait_str is None:
        bait_str = parse_template_param(block, "bait")
    if bait_str and bait_str.strip().lower() not in ("no", "none", "n/a"):
        for part in re.split(r",\s*(?:or\s+)?|\s+or\s+", bait_str):
            bait_name = clean_name(part, page_name)
            if bait_name:
                action["input_items"].append(bait_name)

    return action


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

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
            all_actions.extend(parse_hunter_actions(block, page_name))

    # Dedup by name — each creature should appear once
    seen: dict[str, dict] = {}
    for action in all_actions:
        key = action["name"]
        if key not in seen:
            seen[key] = action

    deduped_actions = list(seen.values())
    print(f"Parsed {len(all_actions)} raw, {len(deduped_actions)} after dedup")

    action_count = 0

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

        # Skills → requirement groups; XP → output experience
        for skill in action["skills"]:
            group_id = create_requirement_group(conn)
            add_group_requirement(conn, group_id, "group_skill_requirements", {
                "skill": skill["skill"],
                "level": skill["level"],
                "boostable": 0,
            })
            link_requirement_group(
                conn, "action_requirement_groups", "action_id", action_id, group_id,
            )
            if skill["xp"] > 0:
                conn.execute(
                    "INSERT OR IGNORE INTO action_output_experience (action_id, skill, xp) VALUES (?, ?, ?)",
                    (action_id, skill["skill"], skill["xp"]),
                )

        # Output item — the caught creature
        creature_item_id = resolve_item(action["name"])
        if creature_item_id is not None:
            conn.execute(
                "INSERT INTO action_output_items (action_id, item_id, item_name, quantity) VALUES (?, ?, ?, 1)",
                (action_id, creature_item_id, action["name"]),
            )
        else:
            conn.execute(
                "INSERT INTO action_output_objects (action_id, object_name) VALUES (?, ?)",
                (action_id, action["name"]),
            )

        # Trap/tool → requirement groups (each tool is its own group)
        for tool_name in action["tools"]:
            tool_item_id = resolve_item(tool_name)
            if tool_item_id is not None:
                group_id = create_requirement_group(conn)
                add_group_requirement(conn, group_id, "group_item_requirements", {
                    "item_id": tool_item_id,
                    "quantity": 1,
                })
                link_requirement_group(
                    conn, "action_requirement_groups", "action_id", action_id, group_id,
                )

        # Bait → input items (OR'd in one group if multiple options)
        if action["input_items"]:
            group_id = create_requirement_group(conn)
            for bait_name in action["input_items"]:
                bait_item_id = resolve_item(bait_name)
                if bait_item_id is not None:
                    conn.execute(
                        "INSERT INTO action_input_items (action_id, item_id, item_name, quantity) VALUES (?, ?, ?, 1)",
                        (action_id, bait_item_id, bait_name),
                    )
                    add_group_requirement(conn, group_id, "group_item_requirements", {
                        "item_id": bait_item_id,
                        "quantity": 1,
                    })
            link_requirement_group(
                conn, "action_requirement_groups", "action_id", action_id, group_id,
            )

        action_count += 1

    conn.commit()
    print(f"Inserted {action_count} hunter actions")

    # Record attributions
    table_names = ["actions", "action_output_experience", "action_input_items",
                    "action_output_items", "action_output_objects"]
    record_attributions_batch(conn, table_names, list(all_wikitext.keys()))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch hunter actions from the OSRS wiki")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
