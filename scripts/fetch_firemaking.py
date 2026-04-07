"""Fetch firemaking actions from the OSRS wiki and populate the action tables.

Parses {{Firemaking info}} templates from pages that transclude them. Standard
log burning has versions for each method (tinderbox, bow, barbarian pyre,
bonfire) with different level requirements and tools. Pyre cremation has
versions for each shade remains type with varying Prayer XP. The logs are
input items consumed by the action.

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
    strip_wiki_links,
    throttle,
)

# Standard firemaking burns one log every 4 game ticks (2.4 seconds).
FIREMAKING_TICKS = 4

_PAREN_SUFFIX = re.compile(r"^(.+?)\s*\([^)]+\)$")


def _parse_facility(facility: str | None) -> str | None:
    """Extract facility name, or None if N/A."""
    if not facility or facility.strip().upper() == "N/A":
        return None
    cleaned = strip_wiki_links(facility).strip()
    # Take first option if "X or Y"
    if " or " in cleaned:
        cleaned = cleaned.split(" or ")[0].strip()
    return cleaned if cleaned else None


def _parse_logs(block: str, page_name: str, members: int, versions: list[str]) -> list[dict]:
    """Parse standard log burning (tinderbox, bow, barbarian pyre, bonfire)."""
    if not versions:
        # Unversioned — single method
        level = parse_int(parse_template_param(block, "skill1lvl"))
        if level is None:
            level = parse_int(parse_template_param(block, "level"))
        if level is None:
            return []
        xp = parse_xp(parse_template_param(block, "skill1exp") or parse_template_param(block, "xp"))
        tool_str = parse_template_param(block, "tool")
        tool = clean_name(tool_str, page_name) if tool_str and tool_str.strip().upper() != "N/A" else None
        at = _parse_facility(parse_template_param(block, "facility"))
        return [{
            "name": page_name,
            "page": page_name,
            "members": members,
            "ticks": FIREMAKING_TICKS,
            "notes": None,
            "at": at,
            "level": level,
            "xp": xp,
            "tool": tool,
            "secondary_skill": None,
            "secondary_level": None,
            "secondary_xp": 0.0,
            "remains": None,
        }]

    actions = []
    for vi, version_name in enumerate(versions, 1):
        level = parse_int(parse_template_param(block, f"skill1lvl{vi}"))
        if level is None:
            continue
        xp = parse_xp(parse_template_param(block, f"skill1exp{vi}"))

        tool_str = parse_template_param(block, f"tool{vi}")
        tool = clean_name(tool_str, page_name) if tool_str and tool_str.strip().upper() != "N/A" else None

        at = _parse_facility(parse_template_param(block, f"facility{vi}"))

        # First version (Tinderbox) uses bare page name; others get a suffix
        action_name = page_name if vi == 1 else f"{page_name} ({version_name})"

        action = {
            "name": action_name,
            "page": page_name,
            "members": members,
            "ticks": FIREMAKING_TICKS,
            "notes": version_name if vi > 1 else None,
            "at": at,
            "level": level,
            "xp": xp,
            "tool": tool,
            "secondary_skill": None,
            "secondary_level": None,
            "secondary_xp": 0.0,
            "remains": None,
        }

        # Barbarian pyre has secondary Crafting requirement and XP
        if "pyre" in version_name.lower():
            craft_level = parse_int(parse_template_param(block, f"skill2lvl{vi}"))
            craft_xp = parse_xp(parse_template_param(block, "craftxp"))
            if craft_level:
                action["secondary_skill"] = Skill.CRAFTING
                action["secondary_level"] = craft_level
                action["secondary_xp"] = craft_xp

        actions.append(action)

    return actions


def _parse_pyre(block: str, page_name: str, members: int, versions: list[str]) -> list[dict]:
    """Parse pyre log cremation (Shades of Mort'ton)."""
    level = parse_int(parse_template_param(block, "skill1lvl"))
    if level is None:
        return []
    xp = parse_xp(parse_template_param(block, "skill1exp"))
    prayer_level = parse_int(parse_template_param(block, "skill2lvl"))

    if not versions:
        prayer_xp = parse_xp(parse_template_param(block, "skill2exp"))
        item_str = parse_template_param(block, "item")
        remains = clean_name(item_str, page_name) if item_str else None
        return [{
            "name": page_name,
            "page": page_name,
            "members": members,
            "ticks": None,
            "notes": None,
            "at": "Funeral pyre",
            "level": level,
            "xp": xp,
            "tool": None,
            "secondary_skill": Skill.PRAYER if prayer_level else None,
            "secondary_level": prayer_level,
            "secondary_xp": prayer_xp,
            "remains": remains,
        }]

    actions = []
    for vi, version_name in enumerate(versions, 1):
        prayer_xp = parse_xp(parse_template_param(block, f"skill2exp{vi}"))
        item_str = parse_template_param(block, f"item{vi}")
        remains = clean_name(item_str, page_name) if item_str else None

        actions.append({
            "name": f"{page_name} ({version_name})",
            "page": page_name,
            "members": members,
            "ticks": None,
            "notes": version_name,
            "at": "Funeral pyre",
            "level": level,
            "xp": xp,
            "tool": None,
            "secondary_skill": Skill.PRAYER if prayer_level else None,
            "secondary_level": prayer_level,
            "secondary_xp": prayer_xp,
            "remains": remains,
        })

    return actions


def parse_firemaking_actions(block: str, page_name: str) -> list[dict]:
    """Parse a {{Firemaking info}} block into one or more action dicts."""
    name_raw = parse_template_param(block, "name")
    if not name_raw:
        return []

    members = parse_members(parse_template_param(block, "members"))
    fm_type = (parse_template_param(block, "type") or "").strip().lower()

    versions = detect_versions(block)

    if fm_type == "pyre":
        return _parse_pyre(block, page_name, members, versions)
    else:
        # logs, light, other — all use the standard version pattern
        return _parse_logs(block, page_name, members, versions)


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    # Find all pages that transclude Template:Firemaking info
    print("Finding pages with {{Firemaking info}}...")
    pages = fetch_template_users("Firemaking info")
    print(f"Found {len(pages)} pages")

    # Build item name -> id lookup
    item_rows = conn.execute("SELECT id, name FROM items").fetchall()
    item_lookup: dict[str, int] = {name: id for id, name in item_rows}

    def resolve_item(name: str) -> int | None:
        item_id = item_lookup.get(name)
        if item_id is not None:
            return item_id
        m = _PAREN_SUFFIX.match(name)
        if m:
            return item_lookup.get(m.group(1).strip())
        return None

    # Clear existing firemaking actions for clean re-import
    old_ids = [r[0] for r in conn.execute(
        "SELECT action_id FROM source_actions WHERE source = 'firemaking'"
    ).fetchall()]
    if old_ids:
        placeholders = ",".join("?" * len(old_ids))
        for table in (
            "action_requirement_groups", "action_output_objects", "action_output_items",
            "action_output_experience", "action_input_currencies", "action_input_objects",
            "action_input_items",
        ):
            conn.execute(f"DELETE FROM {table} WHERE action_id IN ({placeholders})", old_ids)
        conn.execute("DELETE FROM source_actions WHERE source = 'firemaking'")
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
        blocks = extract_all_templates(wikitext, "Firemaking info")
        for block in blocks:
            all_actions.extend(parse_firemaking_actions(block, page_name))

    # Dedup by (name) — firemaking pages are per-log-type so overlap is rare,
    # but guard against duplicate template blocks on the same page
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
            "INSERT INTO actions (name, members, ticks, notes, at) VALUES (?, ?, ?, ?, ?)",
            (action["name"], action["members"], action["ticks"], action["notes"], action["at"]),
        )
        action_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO source_actions (source, action_id) VALUES ('firemaking', ?)",
            (action_id,),
        )

        # Firemaking skill requirement
        group_id = create_requirement_group(conn)
        add_group_requirement(conn, group_id, "group_skill_requirements", {
            "skill": Skill.FIREMAKING.value,
            "level": action["level"],
            "boostable": 0,
        })
        link_requirement_group(
            conn, "action_requirement_groups", "action_id", action_id, group_id,
        )

        # Firemaking XP output
        if action["xp"] > 0:
            conn.execute(
                "INSERT OR IGNORE INTO action_output_experience (action_id, skill, xp) VALUES (?, ?, ?)",
                (action_id, Skill.FIREMAKING.value, action["xp"]),
            )

        # Secondary skill requirement + XP (Crafting for barbarian pyre, Prayer for shade pyre)
        if action["secondary_skill"] is not None:
            if action["secondary_level"]:
                group_id = create_requirement_group(conn)
                add_group_requirement(conn, group_id, "group_skill_requirements", {
                    "skill": action["secondary_skill"].value,
                    "level": action["secondary_level"],
                    "boostable": 0,
                })
                link_requirement_group(
                    conn, "action_requirement_groups", "action_id", action_id, group_id,
                )
            if action["secondary_xp"] > 0:
                conn.execute(
                    "INSERT OR IGNORE INTO action_output_experience (action_id, skill, xp) VALUES (?, ?, ?)",
                    (action_id, action["secondary_skill"].value, action["secondary_xp"]),
                )

        # Input item — the logs being burned
        log_name = action["page"]
        log_item_id = resolve_item(log_name)
        if log_item_id is not None:
            conn.execute(
                "INSERT INTO action_input_items (action_id, item_id, item_name, quantity) VALUES (?, ?, ?, 1)",
                (action_id, log_item_id, log_name),
            )

        # Input item — shade remains (pyre type only)
        if action["remains"]:
            remains_item_id = resolve_item(action["remains"])
            if remains_item_id is not None:
                conn.execute(
                    "INSERT INTO action_input_items (action_id, item_id, item_name, quantity) VALUES (?, ?, ?, 1)",
                    (action_id, remains_item_id, action["remains"]),
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
    print(f"Inserted {action_count} firemaking actions")

    # Record attributions
    table_names = ["actions", "action_output_experience", "action_input_items"]
    record_attributions_batch(conn, table_names, list(all_wikitext.keys()))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch firemaking actions from the OSRS wiki")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
