"""Fetch agility actions from the OSRS wiki and populate the action tables.

Parses {{Agility info}} templates from pages that transclude them. Each
obstacle, shortcut, or completion bonus becomes one action (or one per
version for pages with multiple variants).

Agility type (Obstacle, Shortcut, Completion Bonus, etc.) and course name
are stored in notes. Modelled as instant actions — ticks is NULL.

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


def parse_agility_actions(block: str, page_name: str) -> list[dict]:
    """Parse a {{Agility info}} block into one or more action dicts.

    Versioned templates produce one action per version. Unversioned produce
    a single action.
    """
    name_raw = parse_template_param(block, "name")
    target_name = clean_name(name_raw, page_name) if name_raw else page_name

    if not target_name:
        return []

    members = parse_members(parse_template_param(block, "members"))

    # Course link — strip wiki markup
    course_raw = parse_template_param(block, "course")
    course = strip_wiki_links(course_raw).strip() if course_raw else None

    # Type — Obstacle, Shortcut, Completion Bonus, etc.
    agility_type = parse_template_param(block, "type")

    versions = detect_versions(block)

    if not versions:
        action = _parse_single_version(
            block, page_name, target_name, members, agility_type, course, suffix="",
        )
        return [action] if action else []

    actions = []
    for vi, version_name in enumerate(versions, 1):
        suffix = str(vi)
        action = _parse_single_version(
            block, page_name, target_name, members, agility_type, course, suffix=suffix,
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
    agility_type: str | None,
    course: str | None,
    suffix: str,
) -> dict | None:
    """Parse one version of an Agility info block."""
    # Build notes from type and course
    notes_parts = []
    if agility_type:
        notes_parts.append(agility_type.strip())
    if course:
        notes_parts.append(course)
    notes = " — ".join(notes_parts) if notes_parts else None

    action: dict = {
        "name": target_name,
        "page": page_name,
        "members": members,
        "ticks": None,
        "notes": notes,
        "at": None,
        "skills": [],
    }

    # Primary skill — defaults to Agility unless overridden by skill1name
    skill_name_raw = parse_template_param(block, f"skill1name{suffix}")
    if skill_name_raw is None:
        skill_name_raw = parse_template_param(block, "skill1name")
    skill = Skill.AGILITY
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
    if level == 0:
        level = 1

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

    # Secondary skills (up to 5 — e.g. Barbarian Outpost gives Strength XP)
    for si in range(2, 6):
        skill_n_name_raw = parse_template_param(block, f"skill{si}name{suffix}")
        if skill_n_name_raw is None:
            skill_n_name_raw = parse_template_param(block, f"skill{si}name")
        if not skill_n_name_raw:
            continue
        try:
            skill_n = Skill.from_label(skill_n_name_raw.strip())
        except KeyError:
            continue

        skill_n_lvl_str = parse_template_param(block, f"skill{si}lvl{suffix}")
        if skill_n_lvl_str is None:
            skill_n_lvl_str = parse_template_param(block, f"skill{si}lvl")
        skill_n_xp_str = parse_template_param(block, f"skill{si}exp{suffix}")
        if skill_n_xp_str is None:
            skill_n_xp_str = parse_template_param(block, f"skill{si}exp")
        skill_n_level = parse_int(skill_n_lvl_str)
        skill_n_xp = parse_xp(skill_n_xp_str)
        if skill_n_level or skill_n_xp > 0:
            action["skills"].append({
                "skill": skill_n.value,
                "level": skill_n_level or 1,
                "xp": skill_n_xp,
            })

    return action


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    # Find all pages that transclude Template:Agility info
    print("Finding pages with {{Agility info}}...")
    pages = fetch_template_users("Agility info")
    print(f"Found {len(pages)} pages")

    # Clear existing agility actions for clean re-import
    old_ids = [r[0] for r in conn.execute(
        "SELECT action_id FROM source_actions WHERE source = 'agility'"
    ).fetchall()]
    if old_ids:
        placeholders = ",".join("?" * len(old_ids))
        for table in (
            "action_requirement_groups", "action_output_objects", "action_output_items",
            "action_output_experience", "action_input_currencies", "action_input_objects",
            "action_input_items",
        ):
            conn.execute(f"DELETE FROM {table} WHERE action_id IN ({placeholders})", old_ids)
        conn.execute("DELETE FROM source_actions WHERE source = 'agility'")
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
        blocks = extract_all_templates(wikitext, "Agility info")
        for block in blocks:
            all_actions.extend(parse_agility_actions(block, page_name))

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
            "INSERT INTO actions (name, members, ticks, notes, at) VALUES (?, ?, ?, ?, ?)",
            (action["name"], action["members"], action["ticks"], action["notes"], action["at"]),
        )
        action_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO source_actions (source, action_id) VALUES ('agility', ?)",
            (action_id,),
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

        action_count += 1

    conn.commit()
    print(f"Inserted {action_count} agility actions")

    # Record attributions
    table_names = ["actions", "action_output_experience"]
    record_attributions_batch(conn, table_names, list(all_wikitext.keys()))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch agility actions from the OSRS wiki")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
