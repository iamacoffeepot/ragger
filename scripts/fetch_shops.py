"""Fetch shop data from the OSRS wiki and populate shops/shop_items tables.

Parses {{Infobox Shop}}, {{StoreTableHead}}, and {{StoreLine}} templates
from each shop's wiki page.

Requires: fetch_items.py to have been run first (for item cross-referencing).
"""

import argparse
import math
import re
import time
from pathlib import Path

import requests

from clogger.db import create_tables, get_connection
from clogger.enums import Region

API_URL = "https://oldschool.runescape.wiki/api.php"
USER_AGENT = "clogger/0.1 - OSRS Leagues planner"
HEADERS = {"User-Agent": USER_AGENT}


def fetch_shop_pages() -> list[str]:
    """Get all page titles in Category:Shops."""
    pages: list[str] = []
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": "Category:Shops",
        "cmlimit": "500",
        "cmtype": "page",
        "cmnamespace": "0",
        "format": "json",
    }

    while True:
        resp = requests.get(API_URL, params=params, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()

        for member in data["query"]["categorymembers"]:
            pages.append(member["title"])

        if "continue" in data:
            params["cmcontinue"] = data["continue"]["cmcontinue"]
        else:
            break

    return pages


def parse_template_param(wikitext: str, param: str) -> str | None:
    """Extract a single parameter value from wiki template text."""
    match = re.search(rf"\|\s*{param}\s*=\s*([^\n|}}]*)", wikitext)
    return match.group(1).strip() if match else None


def extract_template(wikitext: str, template_name: str) -> str | None:
    """Extract a template block handling nested braces."""
    start = wikitext.find("{{" + template_name)
    if start == -1:
        return None
    depth = 0
    i = start
    while i < len(wikitext):
        if wikitext[i:i + 2] == "{{":
            depth += 1
            i += 2
        elif wikitext[i:i + 2] == "}}":
            depth -= 1
            if depth == 0:
                return wikitext[start + len("{{" + template_name):i]
            i += 2
        else:
            i += 1
    return None


def parse_infobox_shop(wikitext: str) -> dict | None:
    """Extract shop metadata from {{Infobox Shop}}."""
    block = extract_template(wikitext, "Infobox Shop")
    if not block:
        return None
    return {
        "name": parse_template_param(block, "name"),
        "location": parse_template_param(block, "location") or "",
        "owner": parse_template_param(block, "owner"),
        "members": parse_template_param(block, "members"),
        "leagueRegion": parse_template_param(block, "leagueRegion"),
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


def resolve_region(label: str | None) -> int | None:
    """Try to map a leagueRegion label to a Region enum value.

    Handles complex formats like "Misthalin&Morytania&Asgarnia, Misthalin&Fremennik"
    by extracting the first region from the first group.
    Returns None for "no" or empty values.
    """
    if not label:
        return None
    cleaned = re.sub(r"<!--.*?-->", "", label).strip().lower()
    if cleaned in ("no", "n/a", ""):
        return None

    # Take the first group (before any comma)
    first_group = label.split(",")[0].strip()
    # Take the first region (before any &)
    first_region = first_group.split("&")[0].strip()

    try:
        return Region.from_label(first_region).value
    except KeyError:
        print(f"  Warning: unhandled leagueRegion value: {label!r}")
        return None


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    pages = fetch_shop_pages()
    print(f"Found {len(pages)} pages in Category:Shops")

    shop_count = 0
    item_count = 0

    for page in pages:
        resp = requests.get(
            API_URL,
            params={"action": "parse", "page": page, "prop": "wikitext", "format": "json"},
            headers=HEADERS,
        )
        resp.raise_for_status()
        wikitext = resp.json().get("parse", {}).get("wikitext", {}).get("*", "")

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

        conn.execute(
            """INSERT OR IGNORE INTO shops
               (name, location, owner, members, region, sell_multiplier, buy_multiplier, delta)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                infobox["name"],
                infobox["location"],
                infobox["owner"],
                members,
                region,
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
        time.sleep(0.1)

    conn.commit()
    print(f"Inserted {shop_count} shops with {item_count} items into {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch OSRS shop data")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/clogger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
