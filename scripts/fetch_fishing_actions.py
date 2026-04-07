"""Fetch fishing actions from the OSRS wiki and populate the action tables.

Parses {{Fishing info}} templates from pages that transclude them. Each
version (e.g. harpoon vs bare-handed) becomes a separate action. Skills,
tools, and bait map to requirement groups and input items; XP maps to
output experience; the caught fish maps to an output item.

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
_SOURCE = "wiki-fishing"
# Wiki template name whose transclusions are fetched and parsed.
_TEMPLATE = "Fishing info"

# Fishing polls every 5 ticks (3 seconds). Each poll rolls against a
# success formula based on fish type and fishing level. The ticks value
# here is the poll interval, not the expected catch time — a separate
# chance layer on top of actions will model the per-roll probability.
FISHING_POLL_TICKS = 5


def parse_fishing_actions(block: str, page_name: str) -> list[dict]:
    """Parse a {{Fishing info}} block into one or more action dicts.

    Versioned templates (e.g. shark: harpoon vs bare-handed) produce
    one action per version. Unversioned produce a single action.
    """
    name_raw = parse_template_param(block, "name")
    if not name_raw:
        return []
    fish_name = clean_name(name_raw, page_name)
    if not fish_name:
        return []

    members = parse_members(parse_template_param(block, "members"))

    versions = detect_versions(block)

    if not versions:
        # Single version — parameters have no numeric suffix
        action = _parse_single_version(block, page_name, fish_name, members, suffix="")
        return [action] if action else []

    # Multiple versions — parameters get numeric suffix per version
    actions = []
    for vi, version_name in enumerate(versions, 1):
        suffix = str(vi)
        action = _parse_single_version(block, page_name, fish_name, members, suffix=suffix)
        if action:
            action["notes"] = version_name
            actions.append(action)
    return actions


def _parse_single_version(
    block: str, page_name: str, fish_name: str, members: int, suffix: str,
) -> dict | None:
    """Parse one version of a Fishing info block."""
    action: dict = {
        "name": fish_name,
        "members": members,
        "ticks": FISHING_POLL_TICKS,
        "notes": None,
        "trigger_types": TriggerType.CLICK_NPC.mask,
        "skills": [],
        "input_items": [],
        "tools": [],
    }

    # Parse skills (skill1, skill2, ...) with optional per-version suffix
    # Unversioned: skill1lvl, skill1exp
    # Versioned: skill1lvl2 (fishing level for version 2), skill2lvl2 (secondary skill for version 2)
    i = 1
    while True:
        # Skill name: skill2name, skill3name (skill1 is always Fishing)
        if i == 1:
            skill = Skill.FISHING
        else:
            # Check versioned skill name first (e.g. skill2name2), then unversioned (skill2name)
            skill_name = parse_template_param(block, f"skill{i}name{suffix}")
            if not skill_name:
                skill_name = parse_template_param(block, f"skill{i}name")
            if not skill_name:
                break
            try:
                skill = Skill.from_label(skill_name.strip())
            except KeyError:
                i += 1
                continue

        # Level: versioned first (skill1lvl2), then unversioned (skill1lvl)
        level_str = parse_template_param(block, f"skill{i}lvl{suffix}")
        if level_str is None:
            level_str = parse_template_param(block, f"skill{i}lvl")
        level = parse_int(level_str)
        if level is None and i == 1:
            # Fishing level from shorthand "level" param
            level = parse_int(parse_template_param(block, "level"))
        if level is None:
            i += 1
            continue

        # XP: versioned first (skill1exp2), then unversioned (skill1exp)
        xp_str = parse_template_param(block, f"skill{i}exp{suffix}")
        if xp_str is None:
            xp_str = parse_template_param(block, f"skill{i}exp")
        # Shorthand "xp" param for fishing XP
        if xp_str is None and i == 1:
            xp_str = parse_template_param(block, "xp")
        xp = parse_xp(xp_str)

        action["skills"].append({
            "skill": skill.value,
            "level": level,
            "xp": xp,
        })
        i += 1

    if not action["skills"]:
        return None

    # Tool: versioned (tool2), then unversioned (tool)
    tool_str = parse_template_param(block, f"tool{suffix}")
    if tool_str is None:
        tool_str = parse_template_param(block, "tool")
    if tool_str and tool_str.strip().lower() not in ("no", "none", "n/a"):
        tool_name = clean_name(tool_str, page_name)
        if tool_name:
            action["tools"].append(tool_name)

    # Bait: versioned (bait2), then unversioned (bait) — becomes input item
    bait_str = parse_template_param(block, f"bait{suffix}")
    if bait_str is None:
        bait_str = parse_template_param(block, "bait")
    if bait_str and bait_str.strip().lower() not in ("no", "none", "n/a"):
        # Bait can be comma/or-separated list: "Fishing bait, Fish offcuts, Feather, Roe, or Caviar"
        # These are OR options — any one works. Store as separate input items (they'll be in same group).
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

    action_count = 0

    # Fetch wikitext in batches of 50
    all_wikitext: dict[str, str] = {}
    for i in range(0, len(pages), WIKI_BATCH_SIZE):
        batch = pages[i:i + WIKI_BATCH_SIZE]
        print(f"  Fetching pages {i + 1}-{i + len(batch)} of {len(pages)}...")
        all_wikitext.update(fetch_pages_wikitext_batch(batch))

    print(f"Fetched {len(all_wikitext)} pages, parsing...")

    for page_name, wikitext in all_wikitext.items():
        blocks = extract_all_templates(wikitext, _TEMPLATE)
        for block in blocks:
            actions = parse_fishing_actions(block, page_name)

            for action in actions:
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

                # Output item — the caught fish
                fish_item_id = resolve_item(action["name"])
                if fish_item_id is not None:
                    conn.execute(
                        "INSERT INTO action_output_items (action_id, item_id, item_name, quantity) VALUES (?, ?, ?, 1)",
                        (action_id, fish_item_id, action["name"]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO action_output_objects (action_id, object_name) VALUES (?, ?)",
                        (action_id, action["name"]),
                    )

                # Tool → requirement group
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
    print(f"Inserted {action_count} fishing actions")

    # Record attributions
    table_names = ["actions", "action_output_experience", "action_input_items",
                    "action_output_items", "action_output_objects"]
    record_attributions_batch(conn, table_names, list(all_wikitext.keys()))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch fishing actions from the OSRS wiki")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
