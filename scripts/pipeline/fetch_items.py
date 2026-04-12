"""Fetch all OSRS items from the wiki API and insert into the items table.

Pulls item names from Category:Items, then batch-fetches wikitext to parse
members, tradeable, weight, game_id, and examine from {{Infobox Item}}.
"""

import argparse
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.wiki import (
    extract_template,
    fetch_category_members,
    fetch_pages_wikitext_batch,
    parse_int,
    parse_template_param,
    populate_aliases_table,
    record_attributions_batch,
    strip_wiki_links,
)


def parse_float(val: str | None) -> float | None:
    if not val:
        return None
    val = val.strip().replace(",", "").replace("kg", "").strip()
    try:
        return float(val)
    except ValueError:
        return None


def parse_bool(val: str | None) -> int | None:
    if not val:
        return None
    cleaned = val.strip().lower()
    if cleaned in ("yes", "true", "1"):
        return 1
    if cleaned in ("no", "false", "0"):
        return 0
    return None


def parse_item(name: str, wikitext: str) -> dict:
    """Parse item metadata from a page's wikitext."""
    item: dict = {"name": name, "game_ids": []}

    block = extract_template(wikitext, "Infobox Item")
    if not block:
        return item

    item["members"] = parse_bool(parse_template_param(block, "members"))
    item["tradeable"] = parse_bool(parse_template_param(block, "tradeable"))
    item["weight"] = parse_float(parse_template_param(block, "weight"))
    item["value"] = parse_int(parse_template_param(block, "value"))

    raw_id = parse_template_param(block, "id")
    game_ids: list[int] = []
    if raw_id:
        for part in raw_id.split(","):
            gid = parse_int(part)
            if gid is not None:
                game_ids.append(gid)
    item["game_ids"] = game_ids

    examine = parse_template_param(block, "examine")
    if examine:
        examine = strip_wiki_links(examine)
    item["examine"] = examine

    return item


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    pages = fetch_category_members(
        "Items",
        exclude_prefixes=("Items/",),
        exclude_titles={"Items"},
        exclude_namespaces={2},
    )
    print(f"Found {len(pages)} items in Category:Items")

    conn = get_connection(db_path)

    # Insert names first so other scripts can reference items by id
    conn.executemany(
        "INSERT OR IGNORE INTO items (name) VALUES (?)",
        [(page,) for page in pages],
    )
    conn.commit()
    print(f"Inserted {conn.total_changes} new item names")

    # Batch-fetch wikitext and parse metadata
    all_wikitext: dict[str, str] = {}
    for i in range(0, len(pages), 50):
        batch = pages[i:i + 50]
        print(f"  Fetching pages {i + 1}-{i + len(batch)}...")
        all_wikitext.update(fetch_pages_wikitext_batch(batch))

    print(f"Fetched {len(all_wikitext)} pages, parsing...")

    # Build name → id lookup for game_id inserts
    item_lookup: dict[str, int] = {
        name: id for id, name in conn.execute("SELECT id, name FROM items").fetchall()
    }

    updated = 0
    game_id_count = 0
    for page_name, wikitext in all_wikitext.items():
        item = parse_item(page_name, wikitext)

        # Update metadata columns
        if any(item.get(k) is not None for k in ("members", "tradeable", "weight", "examine", "value")):
            conn.execute(
                """UPDATE items SET members = ?, tradeable = ?, weight = ?, examine = ?, value = ?
                   WHERE name = ?""",
                (item.get("members"), item.get("tradeable"), item.get("weight"),
                 item.get("examine"), item.get("value"), page_name),
            )
            updated += 1

        # Insert game IDs into junction table
        item_id = item_lookup.get(page_name)
        if item_id and item["game_ids"]:
            conn.executemany(
                "INSERT OR IGNORE INTO item_game_ids (item_id, game_id) VALUES (?, ?)",
                [(item_id, gid) for gid in item["game_ids"]],
            )
            game_id_count += len(item["game_ids"])

    conn.commit()
    print(f"Updated metadata for {updated} items, inserted {game_id_count} game IDs")

    # Fetch wiki redirects as item aliases (e.g. "Amulet of ghostspeak" → "Ghostspeak amulet")
    print("Fetching item aliases from wiki redirects...")
    alias_count = populate_aliases_table(
        conn,
        pages,
        "INSERT OR IGNORE INTO item_aliases (item_id, alias) VALUES (?, ?)",
        page_to_key=item_lookup.get,
    )
    print(f"Inserted {alias_count} item aliases")

    # Generate base-form aliases for parenthetical items: "Clue scroll (easy)"
    # → alias "Clue scroll". Many dialogue conditions reference items by their
    # base name without the variant suffix.
    import re
    paren_pattern = re.compile(r"^(.+?)\s*\(")
    existing_aliases = {
        row[0].lower()
        for row in conn.execute("SELECT alias FROM item_aliases").fetchall()
    }
    existing_names = {name.lower() for name in item_lookup}
    base_rows: list[tuple[int, str]] = []
    for page_name, item_id in item_lookup.items():
        m = paren_pattern.match(page_name)
        if not m:
            continue
        base = m.group(1).strip()
        if len(base) < 4:
            continue
        if base.lower() in existing_names or base.lower() in existing_aliases:
            continue
        base_rows.append((item_id, base))
        existing_aliases.add(base.lower())  # dedup across variants
    conn.executemany(
        "INSERT OR IGNORE INTO item_aliases (item_id, alias) VALUES (?, ?)",
        base_rows,
    )
    conn.commit()
    print(f"Generated {len(base_rows)} base-form aliases from parenthetical items")

    # Record attributions
    record_attributions_batch(conn, "items", list(all_wikitext.keys()))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch OSRS items into the database")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
