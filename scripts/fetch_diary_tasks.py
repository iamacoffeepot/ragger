"""Fetch all OSRS achievement diary tasks from the wiki API and insert into the diary_tasks table.

Also extracts skill and quest requirements for each task.
"""

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

from clogger.db import create_tables, get_connection
from clogger.enums import DiaryLocation
from clogger.wiki import (
    fetch_page_wikitext_with_attribution,
    link_requirement,
    parse_skill_requirements,
    strip_markup,
    throttle,
)

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
TASK_ROW_PATTERN = re.compile(r"^\|\s*(\d+)\.\s*(.+?)(?:\n|$)", re.MULTILINE)
QUEST_REQ_PATTERN = re.compile(r"\[\[([^]|]+?)(?:\|[^]]+)?\]\]")
STARTED_PATTERN = re.compile(r"[Ss]tarted\s+\[\[([^]|]+?)(?:\|[^]]+)?\]\]")


@dataclass
class DiaryTaskData:
    tier: str
    description: str
    skill_reqs: list[tuple[int, int]] = field(default_factory=list)
    quest_reqs: list[tuple[str, bool]] = field(default_factory=list)


def parse_requirements(req_text: str) -> tuple[list[tuple[int, int]], list[tuple[str, bool]]]:
    """Parse skill and quest requirements from a requirements cell."""
    skill_reqs = parse_skill_requirements(req_text)
    quest_reqs: list[tuple[str, bool]] = []

    # Quest requirements: "Started [[Quest]]" or "Completion of [[Quest]]"
    for match in STARTED_PATTERN.finditer(req_text):
        quest_reqs.append((match.group(1), True))

    # Full completion quest requirements via {{SCP|Quest}} pattern
    if "{{SCP|Quest}}" in req_text or "Completion of" in req_text:
        for match in QUEST_REQ_PATTERN.finditer(req_text):
            quest_name = match.group(1)
            if quest_name.startswith("File:") or quest_name.startswith("Category:"):
                continue
            if any(q == quest_name for q, _ in quest_reqs):
                continue
            pos = match.start()
            context = req_text[max(0, pos - 80):pos]
            if "Completion of" in context or "SCP|Quest" in context:
                quest_reqs.append((quest_name, False))

    return skill_reqs, quest_reqs


def parse_diary_tasks(wikitext: str) -> list[DiaryTaskData]:
    """Parse diary tasks from wikitext with their requirements."""
    tasks: list[DiaryTaskData] = []

    tables = wikitext.split("{|")

    for table in tables:
        tier_match = TIER_PATTERN.search(table)
        if not tier_match:
            continue
        tier = tier_match.group(1)

        rows = table.split("|-")
        for row in rows:
            task_match = TASK_ROW_PATTERN.search(row)
            if not task_match:
                continue

            description = strip_markup(task_match.group(2))
            description = re.sub(r"\s+", " ", description)

            cells = row.split("\n|")
            req_text = cells[-1] if len(cells) > 1 else ""

            skill_reqs, quest_reqs = parse_requirements(req_text)
            tasks.append(DiaryTaskData(tier, description, skill_reqs, quest_reqs))

    return tasks


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    quest_ids = dict(conn.execute("SELECT name, id FROM quests").fetchall())

    total = 0
    skill_req_count = 0
    quest_req_count = 0

    for location, page in DIARY_PAGES.items():
        wikitext = fetch_page_wikitext_with_attribution(conn, page, "diary_tasks")
        tasks = parse_diary_tasks(wikitext)

        for task in tasks:
            conn.execute(
                "INSERT OR IGNORE INTO diary_tasks (location, tier, description) VALUES (?, ?, ?)",
                (location.value, task.tier, task.description),
            )
            diary_task_id = conn.execute(
                "SELECT id FROM diary_tasks WHERE location = ? AND tier = ? AND description = ?",
                (location.value, task.tier, task.description),
            ).fetchone()[0]

            for skill_id, level in task.skill_reqs:
                link_requirement(
                    conn,
                    table="skill_requirements",
                    columns={"skill": skill_id, "level": level},
                    junction_table="diary_task_skill_requirements",
                    entity_column="diary_task_id",
                    entity_id=diary_task_id,
                    requirement_column="skill_requirement_id",
                )
                skill_req_count += 1

            for quest_name, partial in task.quest_reqs:
                req_quest_id = quest_ids.get(quest_name)
                if req_quest_id is None:
                    continue
                link_requirement(
                    conn,
                    table="quest_requirements",
                    columns={"required_quest_id": req_quest_id, "partial": 1 if partial else 0},
                    junction_table="diary_task_quest_requirements",
                    entity_column="diary_task_id",
                    entity_id=diary_task_id,
                    requirement_column="quest_requirement_id",
                )
                quest_req_count += 1

        total += len(tasks)
        print(f"  {location.value}: {len(tasks)} tasks")
        throttle()

    conn.commit()
    print(
        f"\nInserted {total} diary tasks, {skill_req_count} skill requirements, "
        f"{quest_req_count} quest requirements into {db_path}"
    )
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
