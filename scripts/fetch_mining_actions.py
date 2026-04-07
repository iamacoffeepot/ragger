"""Fetch mining actions from the OSRS wiki and populate the action tables.

Parses {{Mining info}} templates from pages that transclude them. Each
version (e.g. Granite 500g/2kg/5kg) becomes a separate action with
different XP. The pickaxe tool becomes a requirement group; the mined
ore maps to an output item.

Requires: fetch_items.py to have been run first (for item_id cross-referencing).
"""

import argparse
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.enums import Skill
from ragger.wiki import (
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

# Mining polls every N ticks depending on pickaxe tier (bronze=8, iron=7,
# steel=6, black/mithril=5, adamant=4, rune=3, dragon+=~2.83, crystal=~2.75).
# Store the worst-case (bronze) as the base; a polymorphic layer will reduce
# this based on the equipped pickaxe at query time.
MINING_POLL_TICKS = 8


def parse_mining_actions(block: str, page_name: str) -> list[dict]:
    """Parse a {{Mining info}} block into one or more action dicts.

    Versioned templates (e.g. Granite: 500g, 2kg, 5kg) produce one action
    per version with different XP. Unversioned produce a single action.
    The page name is used as the action name (the mined product).
    """
    name_raw = parse_template_param(block, "name")
    if not name_raw:
        return []

    members = parse_members(parse_template_param(block, "members"))

    # The rock object to mine at
    rock_raw = parse_template_param(block, "rock")
    if rock_raw:
        at = clean_name(rock_raw, page_name)
    else:
        at = clean_name(name_raw, page_name)

    level_str = parse_template_param(block, "level")
    level = parse_int(level_str)
    if level is None:
        return []

    # Tool (usually Pickaxe)
    tool_str = parse_template_param(block, "tool")
    tool_name = clean_name(tool_str, page_name) if tool_str else None

    versions = detect_versions(block)

    if not versions:
        xp = parse_xp(parse_template_param(block, "xp"))
        action = _build_action(page_name, members, at, level, xp, tool_name, notes=None)
        return [action]

    # Versioned — each version gets its own XP
    actions = []
    for vi, version_name in enumerate(versions, 1):
        xp = parse_xp(parse_template_param(block, f"xp{vi}"))
        action_name = f"{page_name} ({version_name})"
        action = _build_action(action_name, members, at, level, xp, tool_name, notes=version_name)
        actions.append(action)
    return actions


def _build_action(
    name: str, members: int, at: str | None, level: int, xp: float,
    tool_name: str | None, notes: str | None,
) -> dict:
    return {
        "name": name,
        "members": members,
        "ticks": MINING_POLL_TICKS,
        "notes": notes,
        "at": at,
        "level": level,
        "xp": xp,
        "tool": tool_name,
    }


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    # Find all pages that transclude Template:Mining info
    print("Finding pages with {{Mining info}}...")
    pages = fetch_template_users("Mining info")
    print(f"Found {len(pages)} pages")

    # Build item name -> id lookup
    item_rows = conn.execute("SELECT id, name FROM items").fetchall()
    item_lookup: dict[str, int] = {name: id for id, name in item_rows}

    def resolve_item(name: str) -> int | None:
        return item_lookup.get(name)

    # Clear existing mining actions for clean re-import
    old_ids = [r[0] for r in conn.execute(
        "SELECT action_id FROM source_actions WHERE source = 'mining'"
    ).fetchall()]
    if old_ids:
        placeholders = ",".join("?" * len(old_ids))
        for table in (
            "action_requirement_groups", "action_output_objects", "action_output_items",
            "action_output_experience", "action_input_currencies", "action_input_objects",
            "action_input_items",
        ):
            conn.execute(f"DELETE FROM {table} WHERE action_id IN ({placeholders})", old_ids)
        conn.execute("DELETE FROM source_actions WHERE source = 'mining'")
        conn.execute(f"DELETE FROM actions WHERE id IN ({placeholders})", old_ids)
    conn.commit()

    action_count = 0

    # Fetch wikitext in batches of 50
    all_wikitext: dict[str, str] = {}
    for i in range(0, len(pages), 50):
        batch = pages[i:i + 50]
        print(f"  Fetching pages {i + 1}-{i + len(batch)} of {len(pages)}...")
        all_wikitext.update(fetch_pages_wikitext_batch(batch))

    print(f"Fetched {len(all_wikitext)} pages, parsing...")

    # Parse all actions first, then dedup. Both ore pages (e.g. "Copper ore")
    # and rock pages (e.g. "Copper rocks") have Mining info templates with the
    # same data. Ore pages have a |rock= param so their action name differs
    # from their at. Rock pages have name == at. When duplicates exist for the
    # same (at, level) pair, prefer the ore page version.
    all_actions: list[dict] = []
    for page_name, wikitext in all_wikitext.items():
        blocks = extract_all_templates(wikitext, "Mining info")
        for block in blocks:
            all_actions.extend(parse_mining_actions(block, page_name))

    # Dedup: group by (at, level), prefer name != at (ore page)
    seen: dict[tuple, dict] = {}
    for action in all_actions:
        key = (action["at"], action["level"], action.get("notes"))
        existing = seen.get(key)
        if existing is None:
            seen[key] = action
        elif action["name"] != action["at"] and existing["name"] == existing["at"]:
            # Prefer ore page over rock page
            seen[key] = action

    deduped_actions = list(seen.values())
    print(f"Parsed {len(all_actions)} raw, {len(deduped_actions)} after dedup")

    for action in deduped_actions:
                cursor = conn.execute(
                    "INSERT INTO actions (name, members, ticks, notes, at) VALUES (?, ?, ?, ?, ?)",
                    (action["name"], action["members"], action["ticks"], action["notes"], action["at"]),
                )
                action_id = cursor.lastrowid
                conn.execute(
                    "INSERT INTO source_actions (source, action_id) VALUES ('mining', ?)",
                    (action_id,),
                )

                # Skill requirement + XP output
                group_id = create_requirement_group(conn)
                add_group_requirement(conn, group_id, "group_skill_requirements", {
                    "skill": Skill.MINING.value,
                    "level": action["level"],
                    "boostable": 0,
                })
                link_requirement_group(
                    conn, "action_requirement_groups", "action_id", action_id, group_id,
                )
                if action["xp"] > 0:
                    conn.execute(
                        "INSERT OR IGNORE INTO action_output_experience (action_id, skill, xp) VALUES (?, ?, ?)",
                        (action_id, Skill.MINING.value, action["xp"]),
                    )

                # Output item — the mined ore/product
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
    print(f"Inserted {action_count} mining actions")

    # Record attributions
    table_names = ["actions", "action_output_experience", "action_output_items",
                    "action_output_objects"]
    record_attributions_batch(conn, table_names, list(all_wikitext.keys()))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch mining actions from the OSRS wiki")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
