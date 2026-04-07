"""Fetch thieving actions from the OSRS wiki and populate the action tables.

Parses {{Thieving info}} templates from pages that transclude them. Each
thievable target becomes one action (or one per version for pages like
doors/cages with Pick-lock/Force variants).

Tool items (lockpicks, etc.) become tool requirements. The thieving type
(Pickpocket, Stall, Chest, Door) is stored in notes. Modelled as instant
actions — ticks is NULL.

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
_SOURCE = "wiki-thieving"
# Wiki template name whose transclusions are fetched and parsed.
_TEMPLATE = "Thieving info"


def parse_thieving_actions(block: str, page_name: str) -> list[dict]:
    """Parse a {{Thieving info}} block into one or more action dicts.

    Versioned templates (e.g. Pick-lock/Force doors, Regular/Flashing arrow
    chests) produce one action per version. Unversioned produce a single action.
    """
    name_raw = parse_template_param(block, "name")
    target_name = clean_name(name_raw, page_name) if name_raw else page_name

    if not target_name:
        return []

    members = parse_members(parse_template_param(block, "members"))
    thieving_type = parse_template_param(block, "type")

    versions = detect_versions(block)

    if not versions:
        action = _parse_single_version(
            block, page_name, target_name, members, thieving_type, suffix="",
        )
        return [action] if action else []

    actions = []
    for vi, version_name in enumerate(versions, 1):
        suffix = str(vi)
        action = _parse_single_version(
            block, page_name, target_name, members, thieving_type, suffix=suffix,
        )
        if action:
            action["name"] = f"{target_name} ({version_name})"
            actions.append(action)
    return actions


def _parse_single_version(
    block: str,
    page_name: str,
    target_name: str,
    members: int,
    thieving_type: str | None,
    suffix: str,
) -> dict | None:
    """Parse one version of a Thieving info block."""
    # Pickpocketing targets NPCs; stalls/chests/doors are world objects
    if thieving_type and thieving_type.strip().lower() == "pickpocket":
        trigger = TriggerType.CLICK_NPC.mask
    else:
        trigger = TriggerType.CLICK_OBJECT.mask

    action: dict = {
        "name": target_name,
        "page": page_name,
        "members": members,
        "ticks": None,
        "notes": thieving_type,
        "trigger_types": trigger,
        "skills": [],
        "tools": [],
    }

    # Primary skill — defaults to Thieving unless overridden by skill1name{suffix}
    skill_name_raw = parse_template_param(block, f"skill1name{suffix}")
    if skill_name_raw is None:
        skill_name_raw = parse_template_param(block, "skill1name")
    skill = Skill.THIEVING
    if skill_name_raw:
        try:
            skill = Skill.from_label(skill_name_raw.strip())
        except KeyError:
            pass

    # Level: versioned first, then unversioned
    level_str = parse_template_param(block, f"level{suffix}")
    if level_str is None:
        level_str = parse_template_param(block, "level")
    if level_str:
        level_str = re.sub(r"\s*\(.*?\)\s*$", "", level_str)
    level = parse_int(level_str)
    if level is None:
        return None

    # XP: versioned first, then unversioned
    xp_str = parse_template_param(block, f"xp{suffix}")
    if xp_str is None:
        xp_str = parse_template_param(block, "xp")
    xp = parse_xp(xp_str)

    action["skills"].append({
        "skill": skill.value,
        "level": level,
        "xp": xp,
    })

    # Secondary skill (rare — e.g. Ogre Coffin has skill2exp for failure XP)
    skill2_name_raw = parse_template_param(block, f"skill2name{suffix}")
    if skill2_name_raw is None:
        skill2_name_raw = parse_template_param(block, "skill2name")
    if skill2_name_raw:
        try:
            skill2 = Skill.from_label(skill2_name_raw.strip())
        except KeyError:
            skill2 = None
        if skill2:
            skill2_lvl_str = parse_template_param(block, f"skill2lvl{suffix}")
            if skill2_lvl_str is None:
                skill2_lvl_str = parse_template_param(block, "skill2lvl")
            skill2_xp_str = parse_template_param(block, f"skill2exp{suffix}")
            if skill2_xp_str is None:
                skill2_xp_str = parse_template_param(block, "skill2exp")
            skill2_level = parse_int(skill2_lvl_str)
            skill2_xp = parse_xp(skill2_xp_str)
            if skill2_level or skill2_xp > 0:
                action["skills"].append({
                    "skill": skill2.value,
                    "level": skill2_level or 1,
                    "xp": skill2_xp,
                })

    # Tool → requirement group
    tool_str = parse_template_param(block, f"tool{suffix}")
    if tool_str is None:
        tool_str = parse_template_param(block, "tool")
    if tool_str and tool_str.strip().lower() not in ("no", "none", "n/a", ""):
        tool_name = clean_name(tool_str, page_name)
        # Strip parenthetical notes like "(highly recommended)"
        if tool_name:
            tool_name = re.sub(r"\s*\(.*?\)\s*$", "", tool_name).strip()
        if tool_name:
            action["tools"].append(tool_name)

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
            all_actions.extend(parse_thieving_actions(block, page_name))

    # Dedup by name
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

        # Output object — the thieved target
        conn.execute(
            "INSERT INTO action_output_objects (action_id, object_name) VALUES (?, ?)",
            (action_id, action["name"]),
        )

        # Tool → requirement groups (each tool is its own group)
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

        action_count += 1

    conn.commit()
    print(f"Inserted {action_count} thieving actions")

    # Record attributions
    table_names = ["actions", "action_output_experience", "action_output_objects"]
    record_attributions_batch(conn, table_names, list(all_wikitext.keys()))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch thieving actions from the OSRS wiki")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
