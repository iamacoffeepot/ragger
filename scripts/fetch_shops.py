"""Fetch shop data from the OSRS wiki and populate shops/shop_items tables.

Parses {{Infobox Shop}}, {{StoreTableHead}}, and {{StoreLine}} templates
from each shop's wiki page.

Requires: fetch_items.py to have been run first (for item cross-referencing).
"""

import argparse
import re
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.enums import ShopType
from ragger.wiki import (
    extract_template,
    fetch_category_members,
    fetch_page_wikitext,
    parse_template_param,
    record_attributions_batch,
    resolve_region,
    strip_wiki_links,
    throttle,
)


def parse_infobox_shop(wikitext: str) -> dict | None:
    """Extract shop metadata from {{Infobox Shop}}."""
    block = extract_template(wikitext, "Infobox Shop")
    if not block:
        return None
    return {
        "name": parse_template_param(block, "name"),
        "location": strip_wiki_links(parse_template_param(block, "location") or ""),
        "owner": parse_template_param(block, "owner"),
        "members": parse_template_param(block, "members"),
        "leagueRegion": parse_template_param(block, "leagueRegion"),
        "special": parse_template_param(block, "special"),
    }


def parse_store_table_head(wikitext: str) -> dict:
    """Extract pricing multipliers from {{StoreTableHead}}."""
    match = re.search(r"\{\{StoreTableHead([^}]*)\}\}", wikitext)
    if not match:
        return {"sell_multiplier": 1000, "buy_multiplier": 1000, "delta": 0}

    block = match.group(1)
    sell = parse_template_param(block, "sellmultiplier")
    buy = parse_template_param(block, "buymultiplier")
    delta = parse_template_param(block, "delta")

    def parse_int(val: str | None, default: int) -> int:
        if not val:
            return default
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return default

    return {
        "sell_multiplier": parse_int(sell, 1000),
        "buy_multiplier": parse_int(buy, 1000),
        "delta": parse_int(delta, 0),
    }


def parse_store_lines(wikitext: str) -> list[dict]:
    """Extract all {{StoreLine}} entries."""
    items: list[dict] = []
    for match in re.finditer(r"\{\{StoreLine([^}]*)\}\}", wikitext):
        block = match.group(1)
        name = parse_template_param(block, "name")
        if not name:
            continue

        stock_str = parse_template_param(block, "stock")
        if stock_str in ("inf", "∞", "Infinity"):
            stock = -1
        else:
            stock = int(stock_str) if stock_str else 0

        restock_str = parse_template_param(block, "restock")
        restock = int(restock_str) if restock_str and restock_str.isdigit() else 0

        sell_override = parse_template_param(block, "sell")
        buy_override = parse_template_param(block, "buy")

        def safe_int(val: str | None) -> int | None:
            if not val or not val.isdigit():
                return None
            return int(val)

        items.append({
            "name": name,
            "stock": stock,
            "restock": restock,
            "sell_override": safe_int(sell_override),
            "buy_override": safe_int(buy_override),
        })

    return items


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    pages = fetch_category_members("Shops")
    print(f"Found {len(pages)} pages in Category:Shops")

    shop_count = 0
    item_count = 0
    shop_pages: list[str] = []

    for page in pages:
        wikitext = fetch_page_wikitext(page)

        if "{{StoreTableHead" not in wikitext:
            continue

        infobox = parse_infobox_shop(wikitext)
        if not infobox or not infobox["name"]:
            continue

        pricing = parse_store_table_head(wikitext)
        store_lines = parse_store_lines(wikitext)

        if not store_lines:
            continue

        region = resolve_region(infobox["leagueRegion"])
        members = 1 if infobox["members"] != "No" else 0
        shop_type = ShopType.from_label(infobox["special"] or "")

        conn.execute(
            """INSERT OR IGNORE INTO shops
               (name, location, owner, members, region, shop_type, sell_multiplier, buy_multiplier, delta)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                infobox["name"],
                infobox["location"],
                infobox["owner"],
                members,
                region,
                shop_type.value,
                pricing["sell_multiplier"],
                pricing["buy_multiplier"],
                pricing["delta"],
            ),
        )
        shop_row = conn.execute(
            "SELECT id FROM shops WHERE name = ?", (infobox["name"],)
        ).fetchone()
        if not shop_row:
            continue
        shop_id = shop_row[0]

        for item in store_lines:
            conn.execute(
                """INSERT OR IGNORE INTO shop_items
                   (shop_id, item_name, stock, restock, sell_price, buy_price)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    shop_id,
                    item["name"],
                    item["stock"],
                    item["restock"],
                    item["sell_override"],
                    item["buy_override"],
                ),
            )
            item_count += 1

        shop_count += 1
        shop_pages.append(page)
        throttle()

    print("Recording attributions...")
    record_attributions_batch(conn, "shops", shop_pages)

    conn.commit()
    print(f"Inserted {shop_count} shops with {item_count} items into {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch OSRS shop data")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
