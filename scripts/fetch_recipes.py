"""Fetch recipe data from the OSRS wiki and populate the recipe tables.

Finds all pages that transclude {{Recipe}}, parses each Recipe block for
skills, inputs, outputs, tools, ticks, and facilities.

Requires: fetch_items.py to have been run first (for item_id cross-referencing).
"""

import argparse
import re
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.enums import Skill
from ragger.wiki import (
    extract_all_templates,
    fetch_pages_wikitext_batch,
    fetch_template_users,
    parse_template_param,
    record_attributions_batch,
    strip_wiki_links,
    throttle,
)


def parse_int(val: str | None) -> int | None:
    if not val:
        return None
    val = val.strip().replace(",", "")
    try:
        return int(val)
    except ValueError:
        return None


def parse_xp(val: str | None) -> float:
    if not val:
        return 0.0
    val = val.strip().replace(",", "")
    try:
        return float(val)
    except ValueError:
        return 0.0


def parse_ticks(val: str | None) -> int | None:
    if not val:
        return None
    cleaned = val.strip().lower()
    if cleaned in ("na", "n/a", "?", "varies", ""):
        return None
    cleaned = cleaned.replace(",", "")
    try:
        return int(cleaned)
    except ValueError:
        return None


def parse_members(val: str | None) -> int:
    if not val:
        return 1
    return 0 if val.strip().lower() == "no" else 1


def parse_boostable(val: str | None) -> int | None:
    if not val:
        return None
    lower = val.strip().lower()
    if lower == "yes":
        return 1
    if lower == "no":
        return 0
    return None


def parse_skill_name(val: str) -> int | None:
    """Convert a wiki skill name to a Skill enum value."""
    try:
        return Skill.from_label(val.strip()).value
    except KeyError:
        return None


def parse_recipe(block: str) -> dict | None:
    """Parse a single {{Recipe}} block into a recipe dict."""
    recipe: dict = {
        "members": parse_members(parse_template_param(block, "members")),
        "ticks": parse_ticks(parse_template_param(block, "ticks")),
        "notes": parse_template_param(block, "notes"),
        "facilities": parse_template_param(block, "facilities"),
        "skills": [],
        "inputs": [],
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
            recipe["skills"].append({
                "skill": skill_id,
                "level": level or 1,
                "xp": parse_xp(parse_template_param(block, f"skill{i}exp")),
                "boostable": parse_boostable(parse_template_param(block, f"skill{i}boostable")),
            })
        i += 1

    # Parse inputs (mat1, mat2, ...)
    i = 1
    while True:
        mat = parse_template_param(block, f"mat{i}")
        if not mat:
            break
        item_name = strip_wiki_links(mat.strip())
        if item_name:
            quantity = parse_int(parse_template_param(block, f"mat{i}quantity")) or 1
            recipe["inputs"].append({
                "item_name": item_name,
                "quantity": quantity,
            })
        i += 1

    # Parse outputs (output1, output2, ...)
    i = 1
    while True:
        output = parse_template_param(block, f"output{i}")
        if not output:
            break
        item_name = strip_wiki_links(output.strip())
        if item_name:
            quantity = parse_int(parse_template_param(block, f"output{i}quantity")) or 1
            recipe["outputs"].append({
                "item_name": item_name,
                "quantity": quantity,
            })
        i += 1

    # Parse tools (comma-separated, each tool is its own group)
    tools_str = parse_template_param(block, "tools")
    if tools_str:
        for group_idx, tool in enumerate(tools_str.split(",")):
            tool_name = strip_wiki_links(tool.strip())
            if tool_name:
                recipe["tools"].append({
                    "tool_group": group_idx,
                    "item_name": tool_name,
                })

    # Skip recipes with no outputs (malformed)
    if not recipe["outputs"]:
        return None

    return recipe


def parse_recipes(wikitext: str) -> list[dict]:
    """Parse all {{Recipe}} blocks from a page's wikitext."""
    blocks = extract_all_templates(wikitext, "Recipe")
    recipes = []
    for block in blocks:
        recipe = parse_recipe(block)
        if recipe:
            recipes.append(recipe)
    return recipes


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    # Find all pages that transclude Template:Recipe
    print("Finding pages with {{Recipe}}...")
    pages = fetch_template_users("Recipe")
    print(f"Found {len(pages)} pages")

    # Build item name -> id lookup with dose/charge suffix fallback
    item_rows = conn.execute("SELECT id, name FROM items").fetchall()
    item_lookup: dict[str, int] = {name: id for id, name in item_rows}
    _dose_pattern = re.compile(r"^(.+?)\s*\((\d+)\)$")

    def resolve_item(name: str) -> int | None:
        item_id = item_lookup.get(name)
        if item_id is not None:
            return item_id
        # Strip dose/charge suffix: "Super restore(4)" -> "Super restore"
        m = _dose_pattern.match(name)
        if m:
            return item_lookup.get(m.group(1).strip())
        return None

    # Clear existing recipe data for clean re-import
    conn.execute("DELETE FROM recipe_tools")
    conn.execute("DELETE FROM recipe_outputs")
    conn.execute("DELETE FROM recipe_inputs")
    conn.execute("DELETE FROM recipe_skills")
    conn.execute("DELETE FROM recipes")
    conn.commit()

    recipe_count = 0

    # Fetch wikitext in batches of 50
    all_wikitext: dict[str, str] = {}
    for i in range(0, len(pages), 50):
        batch = pages[i:i + 50]
        print(f"  Fetching pages {i + 1}-{i + len(batch)} of {len(pages)}...")
        all_wikitext.update(fetch_pages_wikitext_batch(batch))

    print(f"Fetched {len(all_wikitext)} pages, parsing...")

    for page_name, wikitext in all_wikitext.items():
        recipes = parse_recipes(wikitext)

        for recipe in recipes:
            cursor = conn.execute(
                "INSERT INTO recipes (members, ticks, notes, facilities) VALUES (?, ?, ?, ?)",
                (recipe["members"], recipe["ticks"], recipe["notes"], recipe["facilities"]),
            )
            recipe_id = cursor.lastrowid

            for skill in recipe["skills"]:
                conn.execute(
                    "INSERT OR IGNORE INTO recipe_skills (recipe_id, skill, level, xp, boostable) VALUES (?, ?, ?, ?, ?)",
                    (recipe_id, skill["skill"], skill["level"], skill["xp"], skill["boostable"]),
                )

            for inp in recipe["inputs"]:
                conn.execute(
                    "INSERT INTO recipe_inputs (recipe_id, item_id, item_name, quantity) VALUES (?, ?, ?, ?)",
                    (recipe_id, resolve_item(inp["item_name"]), inp["item_name"], inp["quantity"]),
                )

            for out in recipe["outputs"]:
                conn.execute(
                    "INSERT INTO recipe_outputs (recipe_id, item_id, item_name, quantity) VALUES (?, ?, ?, ?)",
                    (recipe_id, resolve_item(out["item_name"]), out["item_name"], out["quantity"]),
                )

            for tool in recipe["tools"]:
                conn.execute(
                    "INSERT INTO recipe_tools (recipe_id, tool_group, item_id, item_name) VALUES (?, ?, ?, ?)",
                    (recipe_id, tool["tool_group"], resolve_item(tool["item_name"]), tool["item_name"]),
                )

            recipe_count += 1

    conn.commit()
    print(f"Inserted {recipe_count} recipes")

    # Record attributions
    table_names = ["recipes", "recipe_skills", "recipe_inputs", "recipe_outputs", "recipe_tools"]
    record_attributions_batch(conn, table_names, list(all_wikitext.keys()))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch recipe data from the OSRS wiki")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
