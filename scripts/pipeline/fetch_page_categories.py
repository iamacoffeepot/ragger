"""Fetch wiki categories for all entity pages and populate page_categories.

Collects distinct page titles from all entity tables, batch-fetches their
categories via prop=categories (50 pages/request), and links them to
wiki_categories rows.
"""

import argparse
from pathlib import Path

import requests

from ragger.db import create_tables, get_connection
from ragger.wiki import API_URL, HEADERS, throttle

ENTITY_TABLES = [
    "items",
    "quests",
    "monsters",
    "npcs",
    "locations",
    "equipment",
    "activities",
    "shops",
]


def collect_page_titles(conn) -> list[str]:
    """Collect distinct page titles from all entity tables."""
    query = " UNION ".join(f"SELECT name FROM {t}" for t in ENTITY_TABLES)
    rows = conn.execute(query).fetchall()
    return sorted(r[0] for r in rows)


def fetch_categories_batch(titles: list[str]) -> dict[str, list[str]]:
    """Batch-fetch categories for up to 50 pages.

    Returns {page_title: [category_name, ...]}.
    """
    result: dict[str, list[str]] = {t: [] for t in titles}
    params = {
        "action": "query",
        "prop": "categories",
        "titles": "|".join(titles),
        "cllimit": "500",
        "clshow": "!hidden",
        "format": "json",
    }

    while True:
        throttle()
        resp = requests.get(API_URL, params=params, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()

        for page in data["query"]["pages"].values():
            title = page.get("title", "")
            for cat in page.get("categories", []):
                cat_name = cat["title"].removeprefix("Category:")
                result.setdefault(title, []).append(cat_name)

        if "continue" in data:
            params["clcontinue"] = data["continue"]["clcontinue"]
        else:
            break

    return result


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    # Build category name -> id lookup
    cat_rows = conn.execute("SELECT id, name FROM wiki_categories").fetchall()
    cat_name_to_id = {r[1]: r[0] for r in cat_rows}

    titles = collect_page_titles(conn)
    print(f"Fetching categories for {len(titles)} pages...")

    conn.execute("DELETE FROM page_categories")
    conn.commit()

    inserted = 0
    for i in range(0, len(titles), 50):
        batch = titles[i : i + 50]
        page_cats = fetch_categories_batch(batch)

        for page_title, cat_names in page_cats.items():
            for cat_name in cat_names:
                cat_id = cat_name_to_id.get(cat_name)
                if cat_id:
                    conn.execute(
                        """INSERT OR IGNORE INTO page_categories
                           (page_title, category_id) VALUES (?, ?)""",
                        (page_title, cat_id),
                    )
                    inserted += 1

        if (i // 50) % 20 == 0:
            conn.commit()
            print(f"  {min(i + 50, len(titles))}/{len(titles)} pages ({inserted} links)")

    conn.commit()
    print(f"Inserted {inserted} page-category links into {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch wiki categories for entity pages"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
