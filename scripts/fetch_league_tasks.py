"""Fetch league tasks from the OSRS wiki and insert into the league_tasks table.

Currently targets Raging Echoes League as a prototype.
Requires: fetch_items.py and fetch_quests.py to have been run first.
"""

import argparse
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

from clogger.db import create_tables, get_connection
from clogger.enums import Region, Skill, TaskDifficulty

API_URL = "https://oldschool.runescape.wiki/api.php"
USER_AGENT = "clogger/0.1 - OSRS Leagues planner"
HEADERS = {"User-Agent": USER_AGENT}

def parse_template_fields(text: str) -> dict[str, str] | None:
    """Parse a RELTaskRow template handling nested [[ ]] and {{ }}."""
    if not text.startswith("{{RELTaskRow|"):
        return None

    # Strip outer {{ }}
    inner = text[2:-2]
    # Skip "RELTaskRow|"
    inner = inner[len("RELTaskRow|"):]

    fields: list[str] = []
    current: list[str] = []
    bracket_depth = 0
    brace_depth = 0

    for ch in inner:
        if ch == "[":
            bracket_depth += 1
            current.append(ch)
        elif ch == "]":
            bracket_depth -= 1
            current.append(ch)
        elif ch == "{":
            brace_depth += 1
            current.append(ch)
        elif ch == "}":
            brace_depth -= 1
            current.append(ch)
        elif ch == "|" and bracket_depth == 0 and brace_depth == 0:
            fields.append("".join(current))
            current = []
        else:
            current.append(ch)
    fields.append("".join(current))

    if len(fields) < 3:
        return None

    result = {"name": fields[0], "description": fields[1]}
    for f in fields[2:]:
        if "=" in f:
            key, _, value = f.partition("=")
            result[key.strip()] = value.strip()

    return result

SKILL_REQ_PATTERN = re.compile(r"\{\{SCP\|(\w+)\|(\d+)")
QUEST_REQ_PATTERN = re.compile(r"\[\[([^]|]+?)(?:\|[^]]+)?\]\]")

SKILL_NAME_MAP = {s.label.lower(): s for s in Skill}

DIFFICULTY_MAP = {
    "easy": TaskDifficulty.EASY,
    "medium": TaskDifficulty.MEDIUM,
    "hard": TaskDifficulty.HARD,
    "elite": TaskDifficulty.ELITE,
    "master": TaskDifficulty.MASTER,
}

REGION_MAP = {
    "asgarnia": Region.ASGARNIA,
    "desert": Region.DESERT,
    "fremennik": Region.FREMENNIK,
    "kandarin": Region.KANDARIN,
    "karamja": Region.KARAMJA,
    "kourend": Region.KOUREND,
    "misthalin": Region.MISTHALIN,
    "morytania": Region.MORYTANIA,
    "tirannwn": Region.TIRANNWN,
    "wilderness": Region.WILDERNESS,
    "general": None,
}


@dataclass
class LeagueTaskData:
    id: int
    name: str
    description: str
    difficulty: TaskDifficulty
    region: Region | None
    skill_reqs: list[tuple[int, int]] = field(default_factory=list)
    quest_reqs: list[tuple[str, bool]] = field(default_factory=list)
    item_reqs: list[str] = field(default_factory=list)


def strip_markup(text: str) -> str:
    text = re.sub(r"\[\[([^]|]*\|)?([^]]*)\]\]", r"\2", text)
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    text = re.sub(r"'{2,3}", "", text)
    return text.strip()


def parse_skill_reqs(s_field: str) -> list[tuple[int, int]]:
    reqs = []
    for match in SKILL_REQ_PATTERN.finditer(s_field):
        skill_name = match.group(1).lower()
        level = int(match.group(2))
        skill = SKILL_NAME_MAP.get(skill_name)
        if skill is not None and 1 <= level <= 99:
            reqs.append((skill.value, level))
    return reqs


def parse_other_reqs(
    other_field: str,
) -> tuple[list[tuple[str, bool]], list[str]]:
    quest_reqs: list[tuple[str, bool]] = []
    item_reqs: list[str] = []

    # Quest requirements
    if "Completion of" in other_field or "SCP|Quest" in other_field:
        for match in QUEST_REQ_PATTERN.finditer(other_field):
            quest_name = match.group(1)
            if quest_name.startswith("File:") or quest_name.startswith("Category:"):
                continue
            pos = match.start()
            context = other_field[max(0, pos - 80) : pos]
            if "Completion of" in context or "SCP|Quest" in context:
                quest_reqs.append((quest_name, False))

    if "Started" in other_field:
        for match in re.finditer(r"[Ss]tarted\s+\[\[([^]|]+?)(?:\|[^]]+)?\]\]", other_field):
            name = match.group(1)
            if not any(q == name for q, _ in quest_reqs):
                quest_reqs.append((name, True))

    # Item requirements — links in non-quest, non-region context
    quest_names = {q for q, _ in quest_reqs}
    for match in QUEST_REQ_PATTERN.finditer(other_field):
        name = match.group(1).strip()
        if name in quest_names:
            continue
        if name.startswith("File:") or name.startswith("Category:"):
            continue
        if "#" in name:
            continue
        # Skip region references {{RE|...}}
        pos = match.start()
        before = other_field[max(0, pos - 5) : pos]
        if "RE|" in before or "SCP|" in before:
            continue
        item_reqs.append(name)

    return quest_reqs, item_reqs


def fetch_tasks_wikitext(page: str) -> str:
    resp = requests.get(
        API_URL,
        params={"action": "parse", "page": page, "prop": "wikitext", "format": "json"},
        headers=HEADERS,
    )
    resp.raise_for_status()
    return resp.json()["parse"]["wikitext"]["*"]


def extract_templates(wikitext: str) -> list[str]:
    """Extract all {{RELTaskRow|...}} templates from wikitext."""
    templates = []
    i = 0
    while i < len(wikitext):
        if wikitext[i : i + 12] == "{{RELTaskRow":
            depth = 0
            start = i
            while i < len(wikitext):
                if wikitext[i : i + 2] == "{{":
                    depth += 1
                    i += 2
                elif wikitext[i : i + 2] == "}}":
                    depth -= 1
                    i += 2
                    if depth == 0:
                        templates.append(wikitext[start:i])
                        break
                else:
                    i += 1
        else:
            i += 1
    return templates


def parse_league_tasks(wikitext: str) -> list[LeagueTaskData]:
    tasks = []
    for template in extract_templates(wikitext):
        fields = parse_template_fields(template)
        if fields is None or "id" not in fields or "tier" not in fields:
            continue

        name = fields["name"].strip()
        description = strip_markup(fields["description"].strip())
        s_field = fields.get("s", "")
        other_field = fields.get("other", "")
        tier = fields["tier"].lower()
        region_str = fields.get("region", "general").strip().lower()
        task_id = int(fields["id"])

        difficulty = DIFFICULTY_MAP.get(tier)
        if difficulty is None:
            continue
        region = REGION_MAP.get(region_str)

        skill_reqs = parse_skill_reqs(s_field)
        quest_reqs, item_reqs = parse_other_reqs(other_field)

        tasks.append(LeagueTaskData(
            id=task_id,
            name=name,
            description=description,
            difficulty=difficulty,
            region=region,
            skill_reqs=skill_reqs,
            quest_reqs=quest_reqs,
            item_reqs=item_reqs,
        ))

    return tasks


def ingest(db_path: Path, page: str = "Raging_Echoes_League/Tasks") -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    # Lookup maps
    quest_ids = dict(conn.execute("SELECT name, id FROM quests").fetchall())
    item_ids = dict(conn.execute("SELECT name, id FROM items").fetchall())

    print(f"Fetching tasks from {page}...")
    wikitext = fetch_tasks_wikitext(page)
    tasks = parse_league_tasks(wikitext)

    skill_req_count = 0
    quest_req_count = 0
    item_req_count = 0

    for task in tasks:
        region_val = task.region.value if task.region is not None else None
        conn.execute(
            "INSERT OR IGNORE INTO league_tasks (id, name, description, difficulty, region) VALUES (?, ?, ?, ?, ?)",
            (task.id, task.name, task.description, task.difficulty.value, region_val),
        )

        # Skill requirements
        for skill_id, level in task.skill_reqs:
            conn.execute(
                "INSERT OR IGNORE INTO skill_requirements (skill, level) VALUES (?, ?)",
                (skill_id, level),
            )
            req_id = conn.execute(
                "SELECT id FROM skill_requirements WHERE skill = ? AND level = ?",
                (skill_id, level),
            ).fetchone()[0]
            conn.execute(
                "INSERT OR IGNORE INTO league_task_skill_requirements (league_task_id, skill_requirement_id) VALUES (?, ?)",
                (task.id, req_id),
            )
            skill_req_count += 1

        # Quest requirements
        for quest_name, partial in task.quest_reqs:
            req_quest_id = quest_ids.get(quest_name)
            if req_quest_id is None:
                continue
            partial_int = 1 if partial else 0
            conn.execute(
                "INSERT OR IGNORE INTO quest_requirements (required_quest_id, partial) VALUES (?, ?)",
                (req_quest_id, partial_int),
            )
            req_id = conn.execute(
                "SELECT id FROM quest_requirements WHERE required_quest_id = ? AND partial = ?",
                (req_quest_id, partial_int),
            ).fetchone()[0]
            conn.execute(
                "INSERT OR IGNORE INTO league_task_quest_requirements (league_task_id, quest_requirement_id) VALUES (?, ?)",
                (task.id, req_id),
            )
            quest_req_count += 1

        # Item requirements
        for item_name in task.item_reqs:
            item_id = item_ids.get(item_name)
            if item_id is None:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO item_requirements (item_id, quantity) VALUES (?, ?)",
                (item_id, 1),
            )
            req_id = conn.execute(
                "SELECT id FROM item_requirements WHERE item_id = ? AND quantity = 1",
                (item_id,),
            ).fetchone()[0]
            conn.execute(
                "INSERT OR IGNORE INTO league_task_item_requirements (league_task_id, item_requirement_id) VALUES (?, ?)",
                (task.id, req_id),
            )
            item_req_count += 1

    conn.commit()
    print(
        f"Inserted {len(tasks)} tasks, {skill_req_count} skill requirements, "
        f"{quest_req_count} quest requirements, {item_req_count} item requirements into {db_path}"
    )
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch league tasks into the database")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/clogger.db"),
        help="Path to the SQLite database",
    )
    parser.add_argument(
        "--page",
        default="Raging_Echoes_League/Tasks",
        help="Wiki page to fetch tasks from",
    )
    args = parser.parse_args()
    ingest(args.db, args.page)
