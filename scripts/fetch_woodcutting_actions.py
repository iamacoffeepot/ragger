"""Fetch woodcutting actions from the OSRS wiki and populate the action tables.

Parses {{Woodcutting info}} templates from pages that transclude them. The
tree object maps to `at`, the axe tool becomes a requirement group, and the
chopped logs map to an output item.

Requires: fetch_items.py to have been run first (for item_id cross-referencing).
"""

import argparse
from pathlib import Path

from ragger.action import Action
from ragger.db import create_tables, get_connection
from ragger.enums import Skill, TriggerType
from ragger.wiki import (
    WIKI_BATCH_SIZE,
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
    throttle,
)

# Key used in source_actions to identify rows belonging to this script.
_SOURCE = "wiki-woodcutting"
# Wiki template name whose transclusions are fetched and parsed.
_TEMPLATE = "Woodcutting info"

# Woodcutting polls every 4 ticks (2.4 seconds). Each poll rolls against a
# success formula based on tree type and woodcutting level. The ticks value
# here is the poll interval, not the expected chop time.
WOODCUTTING_POLL_TICKS = 4


def parse_woodcutting_actions(block: str, page_name: str) -> list[dict]:
    """Parse a {{Woodcutting info}} block into an action dict.

    The page name (the logs) is the action name and output item. The tree
    parameter (or name if no tree) is the object you chop at.
    """
    name_raw = parse_template_param(block, "name")
    if not name_raw:
        return []

    members = parse_members(parse_template_param(block, "members"))

    # The tree object to chop
    tree_raw = parse_template_param(block, "tree")
    if tree_raw:
        at = clean_name(tree_raw, page_name)
    else:
        at = clean_name(name_raw, page_name)

    level_str = parse_template_param(block, "level")
    level = parse_int(level_str)
    if level is None:
        return []

    xp = parse_xp(parse_template_param(block, "xp"))

    # Tool (usually Axe)
    tool_str = parse_template_param(block, "tool")
    tool_name = clean_name(tool_str, page_name) if tool_str else None

    return [{
        "name": page_name,
        "members": members,
        "ticks": WOODCUTTING_POLL_TICKS,
        "notes": None,
        "trigger_types": TriggerType.CLICK_OBJECT.mask,
        "source_object": at,
        "level": level,
        "xp": xp,
        "tool": tool_name,
    }]


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

    # Parse all actions first, then dedup. Both log pages (e.g. "Oak logs")
    # and tree pages (e.g. "Oak tree") may have Woodcutting info templates
    # with the same data. When duplicates exist for the same (at, level)
    # pair, prefer the log page version (name != at).
    all_actions: list[dict] = []
    for page_name, wikitext in all_wikitext.items():
        blocks = extract_all_templates(wikitext, _TEMPLATE)
        for block in blocks:
            all_actions.extend(parse_woodcutting_actions(block, page_name))

    # Dedup: group by (source_object, level), prefer name != source_object (log page)
    seen: dict[tuple, dict] = {}
    for action in all_actions:
        key = (action["source_object"], action["level"])
        existing = seen.get(key)
        if existing is None:
            seen[key] = action
        elif action["name"] != action["source_object"] and existing["name"] == existing["source_object"]:
            seen[key] = action

    deduped_actions = list(seen.values())
    print(f"Parsed {len(all_actions)} raw, {len(deduped_actions)} after dedup")

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

        # Skill requirement + XP output
        group_id = create_requirement_group(conn)
        add_group_requirement(conn, group_id, "group_skill_requirements", {
            "skill": Skill.WOODCUTTING.value,
            "level": action["level"],
            "boostable": 0,
        })
        link_requirement_group(
            conn, "action_requirement_groups", "action_id", action_id, group_id,
        )
        if action["xp"] > 0:
            conn.execute(
                "INSERT OR IGNORE INTO action_output_experience (action_id, skill, xp) VALUES (?, ?, ?)",
                (action_id, Skill.WOODCUTTING.value, action["xp"]),
            )

        # Output item — the chopped logs
        item_id = resolve_item(action["name"])
        if item_id is not None:
            conn.execute(
                "INSERT INTO action_output_items (action_id, item_id, item_name, quantity) VALUES (?, ?, ?, 1)",
                (action_id, item_id, action["name"]),
            )
        else:
            conn.execute(
                "INSERT INTO action_output_objects (action_id, object_name) VALUES (?, ?)",
                (action_id, action["name"]),
            )

        # Tool → requirement group
        if action["tool"]:
            tool_item_id = resolve_item(action["tool"])
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
    print(f"Inserted {action_count} woodcutting actions")

    # Record attributions
    table_names = ["actions", "action_output_experience", "action_output_items",
                    "action_output_objects"]
    record_attributions_batch(conn, table_names, list(all_wikitext.keys()))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch woodcutting actions from the OSRS wiki")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
