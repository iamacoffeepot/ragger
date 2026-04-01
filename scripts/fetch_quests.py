"""Fetch all OSRS quests from the wiki API and insert into the quests table."""

import argparse
import re
import time
from pathlib import Path

import requests

from clogger.db import create_tables, get_connection

API_URL = "https://oldschool.runescape.wiki/api.php"
USER_AGENT = "clogger/0.1 - OSRS Leagues planner"
HEADERS = {"User-Agent": USER_AGENT}

# Pages in the Quests category that aren't actual quests
EXCLUDED_PREFIXES = ("Quests/", "Quest ", "Optimal quest guide")
EXCLUDED_SUFFIXES = ("/Quick guide", "/Full guide")
EXCLUDED_NAMESPACES = {2}  # User namespace
EXCLUDED_TITLES = {
    "An Existential Crisis",
    "Burial at Sea",
    "Impending Chaos",
    "Rocking Out",
    "The Blood Moon Rises",
}

QP_PATTERN = re.compile(r"\|\s*qp\s*=\s*(\d+)")


def fetch_quest_names() -> list[str]:
    quests: list[str] = []
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": "Category:Quests",
        "cmlimit": "500",
        "cmtype": "page",
        "format": "json",
    }

    while True:
        resp = requests.get(API_URL, params=params, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()

        for member in data["query"]["categorymembers"]:
            title = member["title"]
            ns = member["ns"]

            if ns in EXCLUDED_NAMESPACES:
                continue
            if title.startswith(EXCLUDED_PREFIXES):
                continue
            if title.endswith(EXCLUDED_SUFFIXES):
                continue
            if title in EXCLUDED_TITLES or title == "Quests":
                continue

            quests.append(title)

        if "continue" in data:
            params["cmcontinue"] = data["continue"]["cmcontinue"]
        else:
            break

    return sorted(quests)


def fetch_quest_points(titles: list[str]) -> dict[str, int]:
    """Fetch quest points for a batch of quest pages."""
    points: dict[str, int] = {}

    # MediaWiki API allows up to 50 titles per request
    for i in range(0, len(titles), 50):
        batch = titles[i : i + 50]
        params = {
            "action": "parse",
            "prop": "wikitext",
            "format": "json",
        }

        for title in batch:
            params["page"] = title
            resp = requests.get(API_URL, params=params, headers=HEADERS)
            resp.raise_for_status()
            data = resp.json()

            wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
            match = QP_PATTERN.search(wikitext)
            points[title] = int(match.group(1)) if match else 0

            time.sleep(0.1)  # rate limit

    return points


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    quest_names = fetch_quest_names()

    print(f"Fetching quest points for {len(quest_names)} quests...")
    quest_points = fetch_quest_points(quest_names)

    conn = get_connection(db_path)
    conn.executemany(
        "INSERT OR IGNORE INTO quests (name, points) VALUES (?, ?)",
        [(name, quest_points.get(name, 0)) for name in quest_names],
    )
    conn.commit()
    print(f"Inserted {conn.total_changes} quests into {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch OSRS quests into the database")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/clogger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
