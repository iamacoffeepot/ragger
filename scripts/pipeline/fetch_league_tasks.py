"""Fetch league tasks from the OSRS wiki and insert into the league_tasks table.

Supports both Raging Echoes (RELTaskRow) and Demonic Pacts (DPLTaskRow) templates.
Requires: fetch_items.py and fetch_quests.py to have been run first.
"""

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

from ragger.db import create_tables, get_connection
from ragger.enums import DiaryLocation, DiaryTier, League, Region, TaskDifficulty

PAGE_LEAGUE_MAP: dict[str, League] = {
    "Raging_Echoes_League/Tasks": League.RAGING_ECHOES,
    "Demonic_Pacts_League/Tasks": League.DEMONIC_PACTS,
}
from ragger.wiki import (
    add_group_requirement,
    create_requirement_group,
    fetch_page_wikitext_with_attribution,
    link_group_requirement,
    link_requirement_group,
    parse_skill_requirements,
    strip_markup,
)

QUEST_REQ_PATTERN = re.compile(r"\[\[([^]|]+?)(?:\|[^]]+)?\]\]")
REGION_REQ_PATTERN = re.compile(r"\{\{(?:RE|DPL)\|(\w+)\}\}")

DIFFICULTY_MAP = {
    "easy": TaskDifficulty.EASY,
    "medium": TaskDifficulty.MEDIUM,
    "hard": TaskDifficulty.HARD,
    "elite": TaskDifficulty.ELITE,
    "master": TaskDifficulty.MASTER,
}

DIARY_LOCATION_MAP = {
    "ardougne": DiaryLocation.ARDOUGNE,
    "desert": DiaryLocation.DESERT,
    "falador": DiaryLocation.FALADOR,
    "fremennik": DiaryLocation.FREMENNIK,
    "kandarin": DiaryLocation.KANDARIN,
    "karamja": DiaryLocation.KARAMJA,
    "kourend & kebos": DiaryLocation.KOUREND_KEBOS,
    "kourend and kebos": DiaryLocation.KOUREND_KEBOS,
    "lumbridge & draynor": DiaryLocation.LUMBRIDGE_DRAYNOR,
    "morytania": DiaryLocation.MORYTANIA,
    "varrock": DiaryLocation.VARROCK,
    "western provinces": DiaryLocation.WESTERN_PROVINCES,
    "wilderness": DiaryLocation.WILDERNESS,
}

DIARY_TIER_MAP = {
    "easy": DiaryTier.EASY,
    "medium": DiaryTier.MEDIUM,
    "hard": DiaryTier.HARD,
    "elite": DiaryTier.ELITE,
}

# Pattern: "Complete the Easy Falador Diary" or "Kourend and Kebos Easy Diary Tasks"
DIARY_TASK_PATTERN = re.compile(
    r"(?:Complete the (\w+) (.+?) Diary|(.+?) (\w+) Diary Tasks)",
    re.IGNORECASE,
)


TASK_TEMPLATES = ("RELTaskRow", "DPLTaskRow")


def parse_template_fields(text: str) -> dict[str, str] | None:
    """Parse a RELTaskRow or DPLTaskRow template handling nested [[ ]] and {{ }}."""
    prefix = None
    for name in TASK_TEMPLATES:
        if text.startswith("{{" + name + "|"):
            prefix = name
            break
    if prefix is None:
        return None

    inner = text[2:-2]
    inner = inner[len(prefix) + 1:]

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


@dataclass
class LeagueTaskData:
    id: int
    name: str
    description: str
    difficulty: TaskDifficulty
    region: Region
    skill_reqs: list[tuple[int, int]] = field(default_factory=list)
    quest_reqs: list[tuple[str, bool]] = field(default_factory=list)
    item_reqs: list[str] = field(default_factory=list)
    diary_reqs: list[tuple[DiaryLocation, DiaryTier]] = field(default_factory=list)
    region_reqs: list[tuple[list[Region], bool]] = field(default_factory=list)


def parse_other_reqs(
    other_field: str,
) -> tuple[list[tuple[str, bool]], list[str], list[tuple[list[Region], bool]]]:
    quest_reqs: list[tuple[str, bool]] = []
    item_reqs: list[str] = []
    region_reqs: list[tuple[list[Region], bool]] = []

    # Quest requirements
    if "Completion of" in other_field or "SCP|Quest" in other_field:
        for match in QUEST_REQ_PATTERN.finditer(other_field):
            quest_name = match.group(1)
            if quest_name.startswith("File:") or quest_name.startswith("Category:"):
                continue
            pos = match.start()
            context = other_field[max(0, pos - 80):pos]
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
        pos = match.start()
        before = other_field[max(0, pos - 5):pos]
        if "RE|" in before or "SCP|" in before:
            continue
        item_reqs.append(name)

    # Region requirements: {{RE|Region}}
    regions: list[Region] = []
    for match in REGION_REQ_PATTERN.finditer(other_field):
        try:
            region = Region.from_label(match.group(1))
            if region not in regions:
                regions.append(region)
        except KeyError:
            pass

    if regions:
        is_any = "Either" in other_field or "either" in other_field or " or " in other_field or "one of" in other_field
        region_reqs.append((regions, is_any))

    return quest_reqs, item_reqs, region_reqs


def extract_templates(wikitext: str) -> list[str]:
    """Extract all {{RELTaskRow|...}} or {{DPLTaskRow|...}} templates from wikitext."""
    templates: list[str] = []
    markers = [("{{" + name, len("{{" + name)) for name in TASK_TEMPLATES]
    i = 0
    while i < len(wikitext):
        matched = any(wikitext[i:i + length] == marker for marker, length in markers)
        if matched:
            depth = 0
            start = i
            while i < len(wikitext):
                if wikitext[i:i + 2] == "{{":
                    depth += 1
                    i += 2
                elif wikitext[i:i + 2] == "}}":
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
    tasks: list[LeagueTaskData] = []
    for template in extract_templates(wikitext):
        fields = parse_template_fields(template)
        if fields is None or "tier" not in fields:
            continue

        name = fields["name"].strip()
        description = strip_markup(fields["description"].strip())
        s_field = fields.get("s", "")
        other_field = fields.get("other", "")
        tier = fields["tier"].lower()
        region_str = fields.get("region", "general").strip().lower()
        task_id = int(fields["id"]) if "id" in fields and fields["id"] != "0" else 0

        difficulty = DIFFICULTY_MAP.get(tier)
        if difficulty is None:
            continue
        try:
            region = Region.from_label(region_str)
        except KeyError:
            raise ValueError(f"Unknown region '{region_str}' for task '{name}' (id={task_id})")

        skill_reqs = parse_skill_requirements(s_field)
        quest_reqs, item_reqs, region_reqs = parse_other_reqs(other_field)

        # Detect diary requirements from task name
        diary_reqs: list[tuple[DiaryLocation, DiaryTier]] = []
        diary_match = DIARY_TASK_PATTERN.search(name)
        if diary_match:
            if diary_match.group(1):
                tier_str = diary_match.group(1).lower()
                loc_str = diary_match.group(2).lower()
            else:
                loc_str = diary_match.group(3).lower()
                tier_str = diary_match.group(4).lower()
            diary_loc = DIARY_LOCATION_MAP.get(loc_str)
            diary_tier = DIARY_TIER_MAP.get(tier_str)
            if diary_loc and diary_tier:
                diary_reqs.append((diary_loc, diary_tier))

        tasks.append(LeagueTaskData(
            id=task_id, name=name, description=description, difficulty=difficulty,
            region=region, skill_reqs=skill_reqs, quest_reqs=quest_reqs,
            item_reqs=item_reqs, diary_reqs=diary_reqs, region_reqs=region_reqs,
        ))

    return tasks


_REQUIREMENT_TABLES = (
    "group_skill_requirements",
    "group_quest_requirements",
    "group_item_requirements",
    "group_diary_requirements",
    "group_region_requirements",
)


def _clear_league_tasks(conn, league: League) -> None:
    """Delete all tasks for a league along with their requirement-group rows.

    Walks league_tasks → league_task_requirement_groups → requirement_groups +
    the per-kind group_*_requirements tables. Without this, re-ingesting a
    league would orphan every row it previously wrote.
    """
    task_ids = [
        r[0] for r in conn.execute(
            "SELECT id FROM league_tasks WHERE league = ?", (league.value,),
        ).fetchall()
    ]
    if not task_ids:
        return

    task_ph = ",".join("?" * len(task_ids))
    group_ids = [
        r[0] for r in conn.execute(
            f"SELECT group_id FROM league_task_requirement_groups "
            f"WHERE league_task_id IN ({task_ph})",
            task_ids,
        ).fetchall()
    ]
    conn.execute(
        f"DELETE FROM league_task_requirement_groups WHERE league_task_id IN ({task_ph})",
        task_ids,
    )
    if group_ids:
        group_ph = ",".join("?" * len(group_ids))
        for table in _REQUIREMENT_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE group_id IN ({group_ph})", group_ids)
        conn.execute(f"DELETE FROM requirement_groups WHERE id IN ({group_ph})", group_ids)
    conn.execute("DELETE FROM league_tasks WHERE league = ?", (league.value,))


def ingest(db_path: Path, page: str = "Raging_Echoes_League/Tasks") -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    league = PAGE_LEAGUE_MAP.get(page)
    if league is None:
        raise ValueError(
            f"Unknown league for page {page!r}; add it to PAGE_LEAGUE_MAP."
        )

    quest_ids = dict(conn.execute("SELECT name, id FROM quests").fetchall())
    item_ids = dict(conn.execute("SELECT name, id FROM items").fetchall())

    print(f"Fetching tasks from {page}...")
    wikitext = fetch_page_wikitext_with_attribution(conn, page, "league_tasks")
    tasks = parse_league_tasks(wikitext)

    # Clear only this league's existing rows (and their requirement groups) so
    # other leagues' task catalogs survive across ingestions. SQLite FKs here
    # don't cascade, so we walk the graph manually.
    _clear_league_tasks(conn, league)

    skill_req_count = 0
    quest_req_count = 0
    item_req_count = 0
    diary_req_count = 0
    region_req_count = 0

    for task in tasks:
        conn.execute(
            "INSERT INTO league_tasks (name, description, difficulty, region, league) "
            "VALUES (?, ?, ?, ?, ?)",
            (task.name, task.description, task.difficulty.value, task.region.value, league.value),
        )
        league_task_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        for skill_id, level in task.skill_reqs:
            link_group_requirement(conn, "group_skill_requirements", {"skill": skill_id, "level": level},
                                   "league_task_requirement_groups", "league_task_id", league_task_id)
            skill_req_count += 1

        for quest_name, partial in task.quest_reqs:
            req_quest_id = quest_ids.get(quest_name)
            if req_quest_id is None:
                continue
            link_group_requirement(conn, "group_quest_requirements",
                                   {"required_quest_id": req_quest_id, "partial": 1 if partial else 0},
                                   "league_task_requirement_groups", "league_task_id", league_task_id)
            quest_req_count += 1

        for item_name in task.item_reqs:
            item_id = item_ids.get(item_name)
            if item_id is None:
                continue
            link_group_requirement(conn, "group_item_requirements", {"item_id": item_id, "quantity": 1},
                                   "league_task_requirement_groups", "league_task_id", league_task_id)
            item_req_count += 1

        for diary_loc, diary_tier in task.diary_reqs:
            link_group_requirement(conn, "group_diary_requirements",
                                   {"location": diary_loc.value, "tier": diary_tier.value},
                                   "league_task_requirement_groups", "league_task_id", league_task_id)
            diary_req_count += 1

        for regions, is_any in task.region_reqs:
            if is_any:
                # OR: all regions in one group
                group_id = create_requirement_group(conn)
                for r in regions:
                    add_group_requirement(conn, group_id, "group_region_requirements", {"region": r.value})
                link_requirement_group(
                    conn, "league_task_requirement_groups", "league_task_id", league_task_id, group_id,
                )
            else:
                # AND: each region in its own group
                for r in regions:
                    link_group_requirement(conn, "group_region_requirements", {"region": r.value},
                                           "league_task_requirement_groups", "league_task_id", league_task_id)
            region_req_count += 1

    conn.commit()
    print(
        f"Inserted {len(tasks)} tasks, {skill_req_count} skill requirements, "
        f"{quest_req_count} quest requirements, {item_req_count} item requirements, "
        f"{diary_req_count} diary requirements, {region_req_count} region requirements into {db_path}"
    )
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch league tasks into the database")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    parser.add_argument(
        "--page",
        default="Demonic_Pacts_League/Tasks",
        help="Wiki page to fetch tasks from",
    )
    args = parser.parse_args()
    ingest(args.db, args.page)
