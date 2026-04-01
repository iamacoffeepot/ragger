"""Fetch all OSRS achievement diary tasks from the wiki API and insert into the diary_tasks table."""

import argparse
import re
import time
from pathlib import Path

import requests

from clogger.db import create_tables, get_connection
from clogger.enums import DiaryLocation

API_URL = "https://oldschool.runescape.wiki/api.php"
USER_AGENT = "clogger/0.1 - OSRS Leagues planner"
HEADERS = {"User-Agent": USER_AGENT}

# Map enum values to wiki page titles
DIARY_PAGES = {
    DiaryLocation.ARDOUGNE: "Ardougne Diary",
    DiaryLocation.DESERT: "Desert Diary",
    DiaryLocation.FALADOR: "Falador Diary",
    DiaryLocation.FREMENNIK: "Fremennik Diary",
    DiaryLocation.KANDARIN: "Kandarin Diary",
    DiaryLocation.KARAMJA: "Karamja Diary",
    DiaryLocation.KOUREND_KEBOS: "Kourend & Kebos Diary",
    DiaryLocation.LUMBRIDGE_DRAYNOR: "Lumbridge & Draynor Diary",
    DiaryLocation.MORYTANIA: "Morytania Diary",
    DiaryLocation.VARROCK: "Varrock Diary",
    DiaryLocation.WESTERN_PROVINCES: "Western Provinces Diary",
    DiaryLocation.WILDERNESS: "Wilderness Diary",
}

TIER_PATTERN = re.compile(r'data-diary-tier="(\w+)"')
# Match task rows: number + description, stripping wiki markup
TASK_ROW_PATTERN = re.compile(r"^\|\s*(\d+)\.\s*(.+?)(?:\n|$)", re.MULTILINE)


def fetch_diary_wikitext(page: str) -> str:
    resp = requests.get(
        API_URL,
        params={"action": "parse", "page": page, "prop": "wikitext", "format": "json"},
        headers=HEADERS,
    )
    resp.raise_for_status()
    return resp.json()["parse"]["wikitext"]["*"]


def strip_markup(text: str) -> str:
    """Remove wiki markup from task descriptions."""
    # Remove links: [[Target|Display]] -> Display, [[Target]] -> Target
    text = re.sub(r"\[\[([^]|]*\|)?([^]]*)\]\]", r"\2", text)
    # Remove templates
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    # Remove italic markup
    text = re.sub(r"'{2,3}", "", text)
    return text.strip()


def parse_diary_tasks(wikitext: str) -> list[tuple[str, str]]:
    """Parse diary tasks from wikitext, returning (tier, description) pairs."""
    tasks: list[tuple[str, str]] = []

    # Split by table start to process each tier's table
    tables = wikitext.split("{|")

    for table in tables:
        tier_match = TIER_PATTERN.search(table)
        if not tier_match:
            continue
        tier = tier_match.group(1)

        # Split table into rows
        rows = table.split("|-")
        for row in rows:
            task_match = TASK_ROW_PATTERN.search(row)
            if task_match:
                description = strip_markup(task_match.group(2))
                # Clean up multi-line descriptions
                description = re.sub(r"\s+", " ", description)
                tasks.append((tier, description))

    return tasks


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    total = 0
    for location, page in DIARY_PAGES.items():
        wikitext = fetch_diary_wikitext(page)
        tasks = parse_diary_tasks(wikitext)

        conn.executemany(
            "INSERT OR IGNORE INTO diary_tasks (location, tier, description) VALUES (?, ?, ?)",
            [(location.value, tier, desc) for tier, desc in tasks],
        )
        total += len(tasks)
        print(f"  {location.value}: {len(tasks)} tasks")
        time.sleep(0.1)

    conn.commit()
    print(f"\nInserted {total} diary tasks into {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch OSRS diary tasks into the database")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/clogger.db"),
        help="Path to the SQLite database",
    )
    args = parser.parse_args()
    ingest(args.db)
