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
    clean_page_reference,
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


def parse_recipe(block: str, page_name: str) -> dict | None:
    """Parse a single {{Recipe}} block into a recipe dict."""
    recipe: dict = {
        "members": parse_members(parse_template_param(block, "members")),
        "ticks": parse_ticks(parse_template_param(block, "ticks")),
        "notes": parse_template_param(block, "notes"),
        "facilities": parse_template_param(block, "facilities"),
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
            recipe["skills"].append({
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
            recipe["input_currencies"].append({
                "currency": clean_page_reference(strip_wiki_links(currency.strip()), page_name),
                "quantity": quantity,
            })
        elif mat:
            item_name = clean_page_reference(strip_wiki_links(mat.strip()), page_name)
            if item_name:
                if item_name in currency_overrides:
                    recipe["input_currencies"].append({
                        "currency": item_name,
                        "quantity": quantity,
                    })
                else:
                    recipe["input_items"].append({
                        "item_name": item_name,
                        "quantity": quantity,
                    })
        i += 1

    # Recipe name from output1 (what this recipe creates)
    output1 = parse_template_param(block, "output1")
    if not output1:
        return None
    recipe["name"] = clean_page_reference(strip_wiki_links(output1.strip()), page_name)
    if not recipe["name"]:
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
            recipe["outputs"].append({
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
                recipe["tools"].append({
                    "tool_group": group_idx,
                    "item_name": tool_name,
                })

    return recipe


def parse_recipes(page_name: str, wikitext: str) -> list[dict]:
    """Parse all {{Recipe}} blocks from a page's wikitext."""
    blocks = extract_all_templates(wikitext, "Recipe")
    recipes = []
    for block in blocks:
        recipe = parse_recipe(block, page_name)
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

    # Clear existing recipe data for clean re-import
    conn.execute("DELETE FROM recipe_tools")
    conn.execute("DELETE FROM recipe_output_objects")
    conn.execute("DELETE FROM recipe_output_items")
    conn.execute("DELETE FROM recipe_input_currencies")
    conn.execute("DELETE FROM recipe_input_objects")
    conn.execute("DELETE FROM recipe_input_items")
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
        recipes = parse_recipes(page_name, wikitext)

        for recipe in recipes:
            cursor = conn.execute(
                "INSERT INTO recipes (name, members, ticks, notes, facilities) VALUES (?, ?, ?, ?, ?)",
                (recipe["name"], recipe["members"], recipe["ticks"], recipe["notes"], recipe["facilities"]),
            )
            recipe_id = cursor.lastrowid

            for skill in recipe["skills"]:
                conn.execute(
                    "INSERT OR IGNORE INTO recipe_skills (recipe_id, skill, level, xp, boostable) VALUES (?, ?, ?, ?, ?)",
                    (recipe_id, skill["skill"], skill["level"], skill["xp"], skill["boostable"]),
                )

            for inp in recipe["input_items"]:
                item_id = resolve_item(inp["item_name"])
                if item_id is not None:
                    conn.execute(
                        "INSERT INTO recipe_input_items (recipe_id, item_id, item_name, quantity) VALUES (?, ?, ?, ?)",
                        (recipe_id, item_id, inp["item_name"], inp["quantity"]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO recipe_input_objects (recipe_id, object_name) VALUES (?, ?)",
                        (recipe_id, inp["item_name"]),
                    )

            for inp in recipe["input_currencies"]:
                conn.execute(
                    "INSERT INTO recipe_input_currencies (recipe_id, currency, quantity) VALUES (?, ?, ?)",
                    (recipe_id, inp["currency"], inp["quantity"]),
                )

            for out in recipe["outputs"]:
                item_id = resolve_item(out["item_name"])
                if item_id is not None:
                    conn.execute(
                        "INSERT INTO recipe_output_items (recipe_id, item_id, item_name, quantity) VALUES (?, ?, ?, ?)",
                        (recipe_id, item_id, out["item_name"], out["quantity"]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO recipe_output_objects (recipe_id, object_name) VALUES (?, ?)",
                        (recipe_id, out["item_name"]),
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
    table_names = ["recipes", "recipe_skills", "recipe_input_items", "recipe_input_objects",
                    "recipe_input_currencies", "recipe_output_items", "recipe_output_objects",
                    "recipe_tools"]
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
