"""Fetch all OSRS quests from the wiki API and insert into the quests table.

Also extracts experience and item rewards from each quest's reward template.
"""

import argparse
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

from clogger.db import create_tables, get_connection
from clogger.enums import ALL_SKILLS_MASK, Skill

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
# Matches {{SCP|Skill|Amount}} for direct XP rewards
XP_REWARD_PATTERN = re.compile(r"\{\{SCP\|(\w+)\|([\d,]+)\}\}")
# Matches item rewards: "N [[Item]]" or just "[[Item]]"
ITEM_REWARD_PATTERN = re.compile(r"(?:(\d[\d,]*)\s+)?\[\[([^]|]+?)(?:\|[^]]+)?\]\]")
# Matches experience lamp/tome descriptions
LAMP_PATTERN = re.compile(
    r"(\d[\d,]*)\s+experience.*?(?:any skill|any combat skill|choice)",
    re.IGNORECASE,
)

SKILL_NAME_MAP = {s.label.lower(): s for s in Skill}


@dataclass
class QuestData:
    name: str
    points: int = 0
    xp_rewards: list[tuple[int, int]] = field(default_factory=list)  # (skill_id, amount)
    lamp_rewards: list[tuple[int, int]] = field(default_factory=list)  # (eligible_mask, amount)
    item_rewards: list[tuple[str, int]] = field(default_factory=list)  # (item_name, quantity)


# Items that are not real item rewards (descriptions, abilities, etc.)
ITEM_REWARD_SKIP = {
    "experience", "quest", "quests", "slayer", "hitpoints", "attack", "strength",
    "defence", "ranged", "prayer", "magic", "runecraft", "construction", "agility",
    "herblore", "thieving", "crafting", "fletching", "hunter", "mining", "smithing",
    "fishing", "cooking", "firemaking", "woodcutting", "farming", "file",
}

COMBAT_SKILLS_MASK = (
    Skill.ATTACK.mask | Skill.STRENGTH.mask | Skill.DEFENCE.mask
    | Skill.RANGED.mask | Skill.PRAYER.mask | Skill.MAGIC.mask | Skill.HITPOINTS.mask
)


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


def parse_amount(s: str) -> int:
    return int(s.replace(",", ""))


def extract_rewards_section(wikitext: str) -> str:
    """Extract just the rewards= section from the Quest rewards template."""
    start = re.search(r"\|rewards\s*=\s*", wikitext)
    if not start:
        return ""
    pos = start.end()
    depth = 0
    result = []
    while pos < len(wikitext):
        if wikitext[pos : pos + 2] == "{{":
            depth += 1
            result.append("{{")
            pos += 2
        elif wikitext[pos : pos + 2] == "}}":
            if depth == 0:
                break
            depth -= 1
            result.append("}}")
            pos += 2
        else:
            result.append(wikitext[pos])
            pos += 1
    return "".join(result)


def parse_quest_wikitext(name: str, wikitext: str) -> QuestData:
    quest = QuestData(name=name)

    # Quest points
    qp_match = QP_PATTERN.search(wikitext)
    quest.points = int(qp_match.group(1)) if qp_match else 0

    rewards_section = extract_rewards_section(wikitext)
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

    # Item rewards — process each bullet line
    for line in rewards_section.split("*"):
        line = line.strip()
        if not line:
            continue
        # Skip lines that are clearly XP rewards
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


def fetch_quest_data(titles: list[str]) -> list[QuestData]:
    """Fetch and parse quest data from wiki pages."""
    quests: list[QuestData] = []

    for title in titles:
        resp = requests.get(
            API_URL,
            params={"action": "parse", "page": title, "prop": "wikitext", "format": "json"},
            headers=HEADERS,
        )
        resp.raise_for_status()
        wikitext = resp.json().get("parse", {}).get("wikitext", {}).get("*", "")
        quests.append(parse_quest_wikitext(title, wikitext))
        time.sleep(0.1)

    return quests


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    quest_names = fetch_quest_names()

    print(f"Fetching data for {len(quest_names)} quests...")
    quest_data = fetch_quest_data(quest_names)

    conn = get_connection(db_path)

    # Insert quests
    conn.executemany(
        "INSERT OR IGNORE INTO quests (name, points) VALUES (?, ?)",
        [(q.name, q.points) for q in quest_data],
    )

    # Build quest name → id map
    quest_ids = dict(conn.execute("SELECT name, id FROM quests").fetchall())

    # Insert experience rewards and link to quests
    xp_count = 0
    for q in quest_data:
        quest_id = quest_ids[q.name]
        for skill_id, amount in q.xp_rewards:
            mask = 1 << skill_id
            conn.execute(
                "INSERT OR IGNORE INTO experience_rewards (eligible_skills, amount) VALUES (?, ?)",
                (mask, amount),
            )
            reward_id = conn.execute(
                "SELECT id FROM experience_rewards WHERE eligible_skills = ? AND amount = ?",
                (mask, amount),
            ).fetchone()[0]
            conn.execute(
                "INSERT OR IGNORE INTO quest_experience_rewards (quest_id, experience_reward_id) VALUES (?, ?)",
                (quest_id, reward_id),
            )
            xp_count += 1
        for mask, amount in q.lamp_rewards:
            conn.execute(
                "INSERT OR IGNORE INTO experience_rewards (eligible_skills, amount) VALUES (?, ?)",
                (mask, amount),
            )
            reward_id = conn.execute(
                "SELECT id FROM experience_rewards WHERE eligible_skills = ? AND amount = ?",
                (mask, amount),
            ).fetchone()[0]
            conn.execute(
                "INSERT OR IGNORE INTO quest_experience_rewards (quest_id, experience_reward_id) VALUES (?, ?)",
                (quest_id, reward_id),
            )
            xp_count += 1

    # Insert item rewards and link to quests
    item_count = 0
    for q in quest_data:
        quest_id = quest_ids[q.name]
        for item_name, quantity in q.item_rewards:
            conn.execute("INSERT OR IGNORE INTO items (name) VALUES (?)", (item_name,))
            item_id = conn.execute(
                "SELECT id FROM items WHERE name = ?", (item_name,)
            ).fetchone()[0]
            conn.execute(
                "INSERT OR IGNORE INTO item_rewards (item_id, quantity) VALUES (?, ?)",
                (item_id, quantity),
            )
            reward_id = conn.execute(
                "SELECT id FROM item_rewards WHERE item_id = ? AND quantity = ?",
                (item_id, quantity),
            ).fetchone()[0]
            conn.execute(
                "INSERT OR IGNORE INTO quest_item_rewards (quest_id, item_reward_id) VALUES (?, ?)",
                (quest_id, reward_id),
            )
            item_count += 1

    conn.commit()
    print(f"Inserted {len(quest_data)} quests, {xp_count} XP rewards, {item_count} item rewards into {db_path}")
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
