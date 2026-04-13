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
    """Extract pricing multipliers and currency from {{StoreTableHead}}.

    The `currency` param is free-text (e.g. "Tokkul", "Slayer reward
    points"); resolution to `physical_currencies` / `virtual_currencies`
    happens during ingest where the DB is available.
    """
    match = re.search(r"\{\{StoreTableHead([^}]*)\}\}", wikitext)
    if not match:
        return {"sell_multiplier": 1000, "buy_multiplier": 1000, "delta": 0, "currency": None}

    block = match.group(1)
    sell = parse_template_param(block, "sellmultiplier")
    buy = parse_template_param(block, "buymultiplier")
    delta = parse_template_param(block, "delta")
    currency = parse_template_param(block, "currency")

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
        "currency": strip_wiki_links(currency).strip() if currency else None,
    }


def resolve_currency(conn, name: str | None) -> tuple[int | None, int | None]:
    """Resolve a currency name into (physical_currency_id, virtual_currency_id).

    Unspecified / unmatched names default to Coins (the most common case —
    the wiki only writes `currency=` when the shop uses something other
    than Coins). Returns (None, None) only if Coins itself can't be found,
    which would mean fetch_currencies hasn't populated physical_currencies.
    """
    if not name:
        name = "Coins"
    row = conn.execute(
        "SELECT id FROM physical_currencies WHERE lower(name) = lower(?)", (name,),
    ).fetchone()
    if row is not None:
        return row[0], None
    row = conn.execute(
        "SELECT id FROM virtual_currencies WHERE lower(name) = lower(?)", (name,),
    ).fetchone()
    if row is not None:
        return None, row[0]
    # Fall back to Coins if the wiki's currency value is ambiguous.
    row = conn.execute(
        "SELECT id FROM physical_currencies WHERE name = 'Coins'",
    ).fetchone()
    return (row[0] if row else None), None


def parse_store_lines(wikitext: str) -> list[dict]:
    """Extract all {{StoreLine}} and {{Tzhaar shop row}} entries.

    TzHaar shops use `{{Tzhaar shop row}}` (same param shape: name, stock,
    restock, optional sell/buy) because they price in Tokkul and layer a
    sell/buy multiplier on top of the default StoreTableHead. Ignoring it
    dropped Mor Ul Rek shops entirely — see #1.
    """
    items: list[dict] = []
    for match in re.finditer(r"\{\{(?:StoreLine|Tzhaar shop row)([^}]*)\}\}", wikitext):
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
        physical_currency_id, virtual_currency_id = resolve_currency(conn, pricing["currency"])

        conn.execute(
            """INSERT OR IGNORE INTO shops
               (name, location, owner, members, region, shop_type,
                sell_multiplier, buy_multiplier, delta,
                physical_currency_id, virtual_currency_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                physical_currency_id,
                virtual_currency_id,
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
