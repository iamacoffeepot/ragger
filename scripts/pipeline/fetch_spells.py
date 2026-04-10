"""Fetch all spells from the OSRS wiki and populate spell tables.

Fetches from Category:Spells, parses {{Infobox Spell}}, resolves
{{RuneReq}} rune names to item IDs, extracts teleport coordinates.
Inserts into combat_spells, utility_spells, or teleport_spells based
on the spell's type field.
"""

import argparse
import re
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.enums import Element, Spellbook
from ragger.wiki import (
    extract_coords,
    extract_template,
    fetch_category_members,
    fetch_pages_wikitext_batch,
    parse_int,
    parse_template_param,
    record_attributions_batch,
    strip_wiki_links,
)

RUNE_REQ_PATTERN = re.compile(r"(\w[\w\s]*?)\s*=\s*(\d+)")
TICKS_PATTERN = re.compile(r"(\d+)")


def parse_rune_cost(wikitext: str) -> list[tuple[str, int]]:
    """Parse {{RuneReq|Fire=3|Air=2|Mind=1}} into [(rune_name, quantity)]."""
    cost_raw = parse_template_param(wikitext, "cost")
    if not cost_raw:
        return []
    runes: list[tuple[str, int]] = []
    for match in RUNE_REQ_PATTERN.finditer(cost_raw):
        name = match.group(1).strip()
        qty = int(match.group(2))
        rune_name = f"{name} rune"
        runes.append((rune_name, qty))
    return runes


def parse_ticks(val: str | None) -> int | None:
    if not val:
        return None
    m = TICKS_PATTERN.search(val)
    return int(m.group(1)) if m else None


def parse_spell(name: str, wikitext: str) -> dict | None:
    """Parse spell metadata from Infobox Spell."""
    block = extract_template(wikitext, "Infobox Spell")
    if not block:
        return None

    spell_type = (parse_template_param(block, "type") or "").strip().lower()
    if spell_type not in ("combat", "utility", "teleport"):
        return None

    members_raw = (parse_template_param(block, "members") or "").strip().lower()
    members = 1 if members_raw in ("yes", "true", "1") else 0

    spellbook_raw = parse_template_param(block, "spellbook") or "Normal"
    try:
        spellbook = Spellbook.from_label(strip_wiki_links(spellbook_raw))
    except ValueError:
        return None

    level = parse_int(parse_template_param(block, "level"))
    if level is None:
        return None

    exp_raw = parse_template_param(block, "exp") or "0"
    try:
        experience = float(exp_raw.strip().replace(",", ""))
    except ValueError:
        experience = 0.0

    speed = parse_ticks(parse_template_param(block, "speed"))
    cooldown = parse_ticks(parse_template_param(block, "cooldown"))
    description = strip_wiki_links(parse_template_param(block, "description") or "").strip()

    spell: dict = {
        "name": name,
        "type": spell_type,
        "members": members,
        "level": level,
        "spellbook": spellbook.value,
        "experience": experience,
        "speed": speed,
        "cooldown": cooldown,
        "description": description or None,
        "runes": parse_rune_cost(block),
    }

    if spell_type == "combat":
        element_raw = parse_template_param(block, "element")
        if element_raw:
            try:
                spell["element"] = Element.from_label(strip_wiki_links(element_raw)).value
            except ValueError:
                spell["element"] = None
        else:
            spell["element"] = None
        spell["max_damage"] = parse_int(parse_template_param(block, "damage"))

    if spell_type == "teleport":
        lectern_raw = parse_template_param(block, "lectern")
        spell["lectern"] = strip_wiki_links(lectern_raw).strip() if lectern_raw else None
        # Extract destination coordinates from Map template
        coords = extract_coords(wikitext)
        if coords:
            spell["dst_x"] = coords[0][0]
            spell["dst_y"] = coords[0][1]
        else:
            spell["dst_x"] = None
            spell["dst_y"] = None
        # Extract destination name
        dest_raw = parse_template_param(block, "description") or ""
        dest_match = re.search(r"[Tt]eleports?\s+(?:the\s+)?(?:caster|player|you)\s+to\s+(?:the\s+)?(?:[\w\s]*?)?\[\[([^\]|]+)", dest_raw)
        if dest_match:
            spell["destination"] = dest_match.group(1).strip()
        else:
            spell["destination"] = name.replace(" Teleport", "") if "Teleport" in name else None

    return spell


def resolve_rune_ids(conn, runes: list[tuple[str, int]]) -> list[tuple[int, int]]:
    """Resolve rune names to item IDs. Returns [(item_id, quantity)]."""
    result: list[tuple[int, int]] = []
    for rune_name, qty in runes:
        row = conn.execute(
            "SELECT id FROM items WHERE name = ?", (rune_name,)
        ).fetchone()
        if row:
            result.append((row[0], qty))
    return result


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    pages = fetch_category_members(
        "Spells",
        exclude_prefixes=("File:", "Category:"),
    )
    print(f"Found {len(pages)} pages in Category:Spells")

    all_wikitext = fetch_pages_wikitext_batch(pages)

    # Clear existing data
    for table in ("combat_spell_runes", "utility_spell_runes", "teleport_spell_runes",
                  "combat_spells", "utility_spells", "teleport_spells"):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()

    combat_count = 0
    utility_count = 0
    teleport_count = 0
    found_pages: list[str] = []

    for page_name in pages:
        wikitext = all_wikitext.get(page_name, "")
        if not wikitext:
            continue

        spell = parse_spell(page_name, wikitext)
        if not spell:
            continue

        found_pages.append(page_name)
        rune_ids = resolve_rune_ids(conn, spell["runes"])

        if spell["type"] == "combat":
            conn.execute(
                """INSERT OR IGNORE INTO combat_spells
                   (name, members, level, spellbook, experience, speed, cooldown,
                    element, max_damage, description)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (spell["name"], spell["members"], spell["level"], spell["spellbook"],
                 spell["experience"], spell["speed"], spell["cooldown"],
                 spell.get("element"), spell.get("max_damage"), spell["description"]),
            )
            spell_id = conn.execute("SELECT id FROM combat_spells WHERE name = ?", (spell["name"],)).fetchone()[0]
            for item_id, qty in rune_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO combat_spell_runes (spell_id, item_id, quantity) VALUES (?, ?, ?)",
                    (spell_id, item_id, qty),
                )
            combat_count += 1

        elif spell["type"] == "utility":
            conn.execute(
                """INSERT OR IGNORE INTO utility_spells
                   (name, members, level, spellbook, experience, speed, cooldown, description)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (spell["name"], spell["members"], spell["level"], spell["spellbook"],
                 spell["experience"], spell["speed"], spell["cooldown"], spell["description"]),
            )
            spell_id = conn.execute("SELECT id FROM utility_spells WHERE name = ?", (spell["name"],)).fetchone()[0]
            for item_id, qty in rune_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO utility_spell_runes (spell_id, item_id, quantity) VALUES (?, ?, ?)",
                    (spell_id, item_id, qty),
                )
            utility_count += 1

        elif spell["type"] == "teleport":
            conn.execute(
                """INSERT OR IGNORE INTO teleport_spells
                   (name, members, level, spellbook, experience, speed,
                    destination, dst_x, dst_y, lectern, description)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (spell["name"], spell["members"], spell["level"], spell["spellbook"],
                 spell["experience"], spell["speed"],
                 spell.get("destination"), spell.get("dst_x"), spell.get("dst_y"),
                 spell.get("lectern"), spell["description"]),
            )
            spell_id = conn.execute("SELECT id FROM teleport_spells WHERE name = ?", (spell["name"],)).fetchone()[0]
            for item_id, qty in rune_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO teleport_spell_runes (spell_id, item_id, quantity) VALUES (?, ?, ?)",
                    (spell_id, item_id, qty),
                )
            teleport_count += 1

    if found_pages:
        record_attributions_batch(conn, "spells", found_pages)

    conn.commit()
    print(f"Inserted {combat_count} combat, {utility_count} utility, {teleport_count} teleport spells into {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch spells from the wiki")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
