"""Fetch all OSRS quests from the wiki API and insert into the quests table.

Also extracts experience and item rewards from each quest's reward template.
"""

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

from clogger.db import create_tables, get_connection
from clogger.enums import ALL_SKILLS_MASK, Skill
from clogger.wiki import (
    SKILL_NAME_MAP,
    extract_section,
    fetch_category_members,
    fetch_page_wikitext,
    link_requirement,
    parse_skill_requirements,
    throttle,
)

# Pages in the Quests category that aren't actual quests
EXCLUDED_PREFIXES = ("Quests/", "Quest ", "Optimal quest guide")
EXCLUDED_SUFFIXES = ("/Quick guide", "/Full guide")
EXCLUDED_TITLES = {
    "An Existential Crisis",
    "Burial at Sea",
    "Impending Chaos",
    "Rocking Out",
    "The Blood Moon Rises",
}

QP_PATTERN = re.compile(r"\|\s*qp\s*=\s*(\d+)")
# Matches {{SCP|Skill|Amount}} for direct XP rewards
XP_REWARD_PATTERN = re.compile(r"\{\{SCP\|(\w+)\|([\d,]+)\}\}")
# Matches item rewards: "N [[Item]]" or just "[[Item]]"
ITEM_REWARD_PATTERN = re.compile(r"(?:(\d[\d,]*)\s+)?\[\[([^]|]+?)(?:\|[^]]+)?\]\]")
# Matches experience lamp/tome descriptions
LAMP_PATTERN = re.compile(
    r"(\d[\d,]*)\s+experience.*?(?:any skill|any combat skill|choice)",
    re.IGNORECASE,
)

# Matches immediate quest requirements: **[[Quest Name]] at depth 2 only
QUEST_REQ_PATTERN = re.compile(r"^\*\*\[\[([^]|]+?)(?:\|[^]]+)?\]\]", re.MULTILINE)
# Matches "Started [[Quest Name]]" for partial requirements
STARTED_QUEST_PATTERN = re.compile(r"[Ss]tarted\s+\[\[([^]|]+?)(?:\|[^]]+)?\]\]")
QP_REQ_PATTERN = re.compile(r"\{\{SCP\|Quest\|(\d+)")


@dataclass
class QuestData:
    name: str
    points: int = 0
    xp_rewards: list[tuple[int, int]] = field(default_factory=list)
    lamp_rewards: list[tuple[int, int]] = field(default_factory=list)
    item_rewards: list[tuple[str, int]] = field(default_factory=list)
    quest_reqs: list[tuple[str, bool]] = field(default_factory=list)
    skill_reqs: list[tuple[int, int]] = field(default_factory=list)
    quest_point_req: int | None = None


# Items that are not real item rewards (descriptions, abilities, etc.)
ITEM_REWARD_SKIP = {
    "experience", "quest", "quests", "slayer", "hitpoints", "attack", "strength",
    "defence", "ranged", "prayer", "magic", "runecraft", "construction", "agility",
    "herblore", "thieving", "crafting", "fletching", "hunter", "mining", "smithing",
    "fishing", "cooking", "firemaking", "woodcutting", "farming", "file",
}

# Overrides for skill requirements that the wiki encodes in non-standard ways
SKILL_REQ_OVERRIDES: dict[str, list[tuple[int, int]]] = {
    "While Guthix Sleeps": [
        (Skill.ATTACK, 65),
        (Skill.STRENGTH, 65),
        (Skill.THIEVING, 72),
        (Skill.MAGIC, 67),
        (Skill.AGILITY, 66),
        (Skill.FARMING, 65),
        (Skill.HERBLORE, 65),
        (Skill.HUNTER, 62),
    ],
}

COMBAT_SKILLS_MASK = (
    Skill.ATTACK.mask | Skill.STRENGTH.mask | Skill.DEFENCE.mask
    | Skill.RANGED.mask | Skill.PRAYER.mask | Skill.MAGIC.mask | Skill.HITPOINTS.mask
)


def parse_amount(s: str) -> int:
    return int(s.replace(",", ""))


def parse_quest_requirements(requirements_section: str) -> list[tuple[str, bool]]:
    """Parse immediate quest requirements from the requirements section."""
    reqs: list[tuple[str, bool]] = []

    for match in STARTED_QUEST_PATTERN.finditer(requirements_section):
        reqs.append((match.group(1), True))

    for line in requirements_section.split("\n"):
        stripped = line.strip()
        if stripped.startswith("**") and not stripped.startswith("***"):
            link_match = re.search(r"\[\[([^]|]+?)(?:\|[^]]+)?\]\]", stripped)
            if link_match:
                quest_name = link_match.group(1)
                if not any(q == quest_name for q, _ in reqs):
                    reqs.append((quest_name, False))

    return reqs


def parse_quest_wikitext(name: str, wikitext: str) -> QuestData:
    quest = QuestData(name=name)

    # Quest points
    qp_match = QP_PATTERN.search(wikitext)
    quest.points = int(qp_match.group(1)) if qp_match else 0

    # Quest requirements
    req_section = extract_section(wikitext, "requirements")
    if req_section:
        quest.quest_reqs = parse_quest_requirements(req_section)

        if name in SKILL_REQ_OVERRIDES:
            quest.skill_reqs = SKILL_REQ_OVERRIDES[name]
        else:
            quest.skill_reqs = parse_skill_requirements(req_section)

        qp_req_match = QP_REQ_PATTERN.search(req_section)
        if qp_req_match:
            quest.quest_point_req = int(qp_req_match.group(1))

    rewards_section = extract_section(wikitext, "rewards")
    if not rewards_section:
        return quest

    # Direct XP rewards: {{SCP|Skill|Amount}}
    for match in XP_REWARD_PATTERN.finditer(rewards_section):
        skill_name = match.group(1).lower()
        amount = parse_amount(match.group(2))
        skill = SKILL_NAME_MAP.get(skill_name)
        if skill is not None:
            quest.xp_rewards.append((skill.value, amount))

    # Lamp/choice XP rewards
    for match in LAMP_PATTERN.finditer(rewards_section):
        amount = parse_amount(match.group(1))
        context = match.group(0).lower()
        if "combat" in context:
            quest.lamp_rewards.append((COMBAT_SKILLS_MASK, amount))
        else:
            quest.lamp_rewards.append((ALL_SKILLS_MASK, amount))

    # Item rewards
    for line in rewards_section.split("*"):
        line = line.strip()
        if not line:
            continue
        if "experience" in line.lower() and XP_REWARD_PATTERN.search(line):
            continue
        if "experience lamp" in line.lower() or "experience tome" in line.lower():
            continue

        for match in ITEM_REWARD_PATTERN.finditer(line):
            qty_str = match.group(1)
            item_name = match.group(2).strip()

            if item_name.lower() in ITEM_REWARD_SKIP:
                continue
            if item_name.startswith("File:"):
                continue

            quantity = parse_amount(qty_str) if qty_str else 1
            quest.item_rewards.append((item_name, quantity))

    return quest


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    quest_names = fetch_category_members(
        "Quests",
        exclude_prefixes=EXCLUDED_PREFIXES,
        exclude_suffixes=EXCLUDED_SUFFIXES,
        exclude_titles=EXCLUDED_TITLES | {"Quests"},
        exclude_namespaces={2},
    )

    print(f"Fetching data for {len(quest_names)} quests...")
    quest_data: list[QuestData] = []
    for title in quest_names:
        wikitext = fetch_page_wikitext(title)
        quest_data.append(parse_quest_wikitext(title, wikitext))
        throttle()

    conn = get_connection(db_path)

    # Insert quests
    conn.executemany(
        "INSERT OR IGNORE INTO quests (name, points) VALUES (?, ?)",
        [(q.name, q.points) for q in quest_data],
    )

    quest_ids = dict(conn.execute("SELECT name, id FROM quests").fetchall())
    item_ids = dict(conn.execute("SELECT name, id FROM items").fetchall())

    xp_count = 0
    for q in quest_data:
        quest_id = quest_ids[q.name]
        for skill_id, amount in q.xp_rewards:
            mask = 1 << skill_id
            link_requirement(conn, "experience_rewards", {"eligible_skills": mask, "amount": amount},
                             "quest_experience_rewards", "quest_id", quest_id, "experience_reward_id")
            xp_count += 1
        for mask, amount in q.lamp_rewards:
            link_requirement(conn, "experience_rewards", {"eligible_skills": mask, "amount": amount},
                             "quest_experience_rewards", "quest_id", quest_id, "experience_reward_id")
            xp_count += 1

    item_count = 0
    for q in quest_data:
        quest_id = quest_ids[q.name]
        for item_name, quantity in q.item_rewards:
            item_id = item_ids.get(item_name)
            if item_id is None:
                continue
            link_requirement(conn, "item_rewards", {"item_id": item_id, "quantity": quantity},
                             "quest_item_rewards", "quest_id", quest_id, "item_reward_id")
            item_count += 1

    qp_req_count = 0
    for q in quest_data:
        if q.quest_point_req is not None:
            quest_id = quest_ids[q.name]
            link_requirement(conn, "quest_point_requirements", {"points": q.quest_point_req},
                             "quest_quest_point_requirements", "quest_id", quest_id, "quest_point_requirement_id")
            qp_req_count += 1

    skill_req_count = 0
    for q in quest_data:
        quest_id = quest_ids[q.name]
        for skill_id, level in q.skill_reqs:
            link_requirement(conn, "skill_requirements", {"skill": skill_id, "level": level},
                             "quest_skill_requirements", "quest_id", quest_id, "skill_requirement_id")
            skill_req_count += 1

    req_count = 0
    for q in quest_data:
        quest_id = quest_ids[q.name]
        for req_name, partial in q.quest_reqs:
            req_quest_id = quest_ids.get(req_name)
            if req_quest_id is None:
                continue
            link_requirement(conn, "quest_requirements", {"required_quest_id": req_quest_id, "partial": 1 if partial else 0},
                             "quest_quest_requirements", "quest_id", quest_id, "quest_requirement_id")
            req_count += 1

    conn.commit()
    print(
        f"Inserted {len(quest_data)} quests, {xp_count} XP rewards, "
        f"{item_count} item rewards, {qp_req_count} QP requirements, "
        f"{skill_req_count} skill requirements, "
        f"{req_count} quest requirements into {db_path}"
    )
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
