"""Fetch recipe-based actions from the OSRS wiki and populate the action tables.

Finds all pages that transclude {{Recipe}}, parses each Recipe block for
skills, inputs, outputs, tools, ticks, and facilities. Skill levels and tools
are stored as requirement groups; XP is stored as output experience.

Requires: fetch_items.py to have been run first (for item_id cross-referencing).
"""

import argparse
import re
from pathlib import Path

from ragger.action import Action
from ragger.db import create_tables, get_connection
from ragger.enums import Skill
from ragger.wiki import (
    add_group_requirement,
    clean_page_reference,
    create_requirement_group,
    extract_all_templates,
    fetch_pages_wikitext_batch,
    fetch_template_users,
    link_requirement_group,
    parse_boostable,
    parse_int,
    parse_members,
    parse_template_param,
    parse_ticks,
    parse_xp,
    record_attributions_batch,
    strip_wiki_links,
    throttle,
)


def parse_skill_name(val: str) -> int | None:
    """Convert a wiki skill name to a Skill enum value."""
    try:
        return Skill.from_label(val.strip()).value
    except KeyError:
        return None


def parse_action(block: str, page_name: str) -> dict | None:
    """Parse a single {{Recipe}} block into an action dict."""
    action: dict = {
        "members": parse_members(parse_template_param(block, "members")),
        "ticks": parse_ticks(parse_template_param(block, "ticks")),
        "notes": parse_template_param(block, "notes"),
        "at": parse_template_param(block, "facilities"),
        "skills": [],
        "input_items": [],
        "input_currencies": [],
        "outputs": [],
        "tools": [],
    }

    # Parse skills (skill1, skill2, ...)
    i = 1
    while True:
        skill_name = parse_template_param(block, f"skill{i}")
        if not skill_name:
            break
        skill_id = parse_skill_name(skill_name)
        if skill_id is not None:
            level = parse_int(parse_template_param(block, f"skill{i}lvl"))
            action["skills"].append({
                "skill": skill_id,
                "level": level or 1,
                "xp": parse_xp(parse_template_param(block, f"skill{i}exp")),
                "boostable": parse_boostable(parse_template_param(block, f"skill{i}boostable")),
            })
        i += 1

    # Names that appear in mat1 but are actually currencies
    currency_overrides = {
        "Nightmare Zone points",
        "Void Knight commendation points",
        "Zeal Tokens",
    }

    # Parse inputs (mat1, mat2, ...) — route to items or currencies
    i = 1
    while True:
        mat = parse_template_param(block, f"mat{i}")
        currency = parse_template_param(block, f"mat{i}currency")
        if not mat and not currency:
            break
        quantity = parse_int(parse_template_param(block, f"mat{i}quantity")) or 1
        if currency:
            action["input_currencies"].append({
                "currency": clean_page_reference(strip_wiki_links(currency.strip()), page_name),
                "quantity": quantity,
            })
        elif mat:
            item_name = clean_page_reference(strip_wiki_links(mat.strip()), page_name)
            if item_name:
                if item_name in currency_overrides:
                    action["input_currencies"].append({
                        "currency": item_name,
                        "quantity": quantity,
                    })
                else:
                    action["input_items"].append({
                        "item_name": item_name,
                        "quantity": quantity,
                    })
        i += 1

    # Action name from output1 (what this action creates)
    output1 = parse_template_param(block, "output1")
    if not output1:
        return None
    action["name"] = clean_page_reference(strip_wiki_links(output1.strip()), page_name)
    if not action["name"]:
        return None

    # Parse outputs (output1, output2, ...)
    i = 1
    while True:
        output = parse_template_param(block, f"output{i}")
        if not output:
            break
        item_name = clean_page_reference(strip_wiki_links(output.strip()), page_name)
        if item_name:
            quantity = parse_int(parse_template_param(block, f"output{i}quantity")) or 1
            action["outputs"].append({
                "item_name": item_name,
                "quantity": quantity,
            })
        i += 1

    # Parse tools (comma-separated, each tool is its own group)
    tools_str = parse_template_param(block, "tools")
    if tools_str:
        for group_idx, tool in enumerate(tools_str.split(",")):
            tool_name = clean_page_reference(strip_wiki_links(tool.strip()), page_name)
            if tool_name:
                action["tools"].append({
                    "tool_group": group_idx,
                    "item_name": tool_name,
                })

    return action


def parse_actions(page_name: str, wikitext: str) -> list[dict]:
    """Parse all {{Recipe}} blocks from a page's wikitext."""
    blocks = extract_all_templates(wikitext, "Recipe")
    actions = []
    for block in blocks:
        action = parse_action(block, page_name)
        if action:
            actions.append(action)
    return actions


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    # Find all pages that transclude Template:Recipe
    print("Finding pages with {{Recipe}}...")
    pages = fetch_template_users("Recipe")
    print(f"Found {len(pages)} pages")

    # Build item name -> id lookup with fallback strategies
    item_rows = conn.execute("SELECT id, name FROM items").fetchall()
    item_lookup: dict[str, int] = {name: id for id, name in item_rows}
    _paren_suffix = re.compile(r"^(.+?)\s*\([^)]+\)$")

    def resolve_item(name: str) -> int | None:
        # Exact match
        item_id = item_lookup.get(name)
        if item_id is not None:
            return item_id
        # Strip any parenthesized suffix: "Super restore(4)", "Granite (5kg)",
        # "Pharaoh's sceptre (uncharged)", "Apple seedling (w)", etc.
        m = _paren_suffix.match(name)
        if m:
            item_id = item_lookup.get(m.group(1).strip())
            if item_id is not None:
                return item_id
        return None

    Action.delete_by_source(conn, "recipe")
    conn.commit()

    action_count = 0

    # Fetch wikitext in batches of 50
    all_wikitext: dict[str, str] = {}
    for i in range(0, len(pages), 50):
        batch = pages[i:i + 50]
        print(f"  Fetching pages {i + 1}-{i + len(batch)} of {len(pages)}...")
        all_wikitext.update(fetch_pages_wikitext_batch(batch))

    print(f"Fetched {len(all_wikitext)} pages, parsing...")

    for page_name, wikitext in all_wikitext.items():
        actions = parse_actions(page_name, wikitext)

        for action in actions:
            cursor = conn.execute(
                "INSERT INTO actions (name, members, ticks, notes, at) VALUES (?, ?, ?, ?, ?)",
                (action["name"], action["members"], action["ticks"], action["notes"], action["at"]),
            )
            action_id = cursor.lastrowid
            conn.execute(
                "INSERT INTO source_actions (source, action_id) VALUES ('recipe', ?)",
                (action_id,),
            )

            # Skill levels → requirement groups; XP → output experience
            for skill in action["skills"]:
                # Skill level as a requirement group
                group_id = create_requirement_group(conn)
                add_group_requirement(conn, group_id, "group_skill_requirements", {
                    "skill": skill["skill"],
                    "level": skill["level"],
                    "boostable": skill["boostable"] if skill["boostable"] is not None else 0,
                })
                link_requirement_group(
                    conn, "action_requirement_groups", "action_id", action_id, group_id,
                )

                # XP as output
                if skill["xp"] > 0:
                    conn.execute(
                        "INSERT OR IGNORE INTO action_output_experience (action_id, skill, xp) VALUES (?, ?, ?)",
                        (action_id, skill["skill"], skill["xp"]),
                    )

            for inp in action["input_items"]:
                item_id = resolve_item(inp["item_name"])
                if item_id is not None:
                    conn.execute(
                        "INSERT INTO action_input_items (action_id, item_id, item_name, quantity) VALUES (?, ?, ?, ?)",
                        (action_id, item_id, inp["item_name"], inp["quantity"]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO action_input_objects (action_id, object_name) VALUES (?, ?)",
                        (action_id, inp["item_name"]),
                    )

            for inp in action["input_currencies"]:
                conn.execute(
                    "INSERT INTO action_input_currencies (action_id, currency, quantity) VALUES (?, ?, ?)",
                    (action_id, inp["currency"], inp["quantity"]),
                )

            for out in action["outputs"]:
                item_id = resolve_item(out["item_name"])
                if item_id is not None:
                    conn.execute(
                        "INSERT INTO action_output_items (action_id, item_id, item_name, quantity) VALUES (?, ?, ?, ?)",
                        (action_id, item_id, out["item_name"], out["quantity"]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO action_output_objects (action_id, object_name) VALUES (?, ?)",
                        (action_id, out["item_name"]),
                    )

            # Tools → requirement groups (one group per tool_group, items within OR'd)
            tool_groups: dict[int, list[dict]] = {}
            for tool in action["tools"]:
                tool_groups.setdefault(tool["tool_group"], []).append(tool)
            for tools in tool_groups.values():
                group_id = create_requirement_group(conn)
                for tool in tools:
                    item_id = resolve_item(tool["item_name"])
                    if item_id is not None:
                        add_group_requirement(conn, group_id, "group_item_requirements", {
                            "item_id": item_id,
                            "quantity": 1,
                        })
                link_requirement_group(
                    conn, "action_requirement_groups", "action_id", action_id, group_id,
                )

            action_count += 1

    conn.commit()
    print(f"Inserted {action_count} actions")

    # Record attributions
    table_names = ["actions", "action_output_experience", "action_input_items",
                    "action_input_objects", "action_input_currencies",
                    "action_output_items", "action_output_objects"]
    record_attributions_batch(conn, table_names, list(all_wikitext.keys()))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch action data from the OSRS wiki")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
