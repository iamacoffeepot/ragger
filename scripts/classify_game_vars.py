"""Classify game variable names using the Claude CLI and validate against the database.

Sends batches of variable names to Claude (Sonnet by default) via the `claude` CLI
for content/functional tag classification. The prompt is seeded with real entity names
from the database so the model prefers known names. Content tags are then validated
against quests, monsters, locations, items, and NPCs tables.

Requires the Claude CLI (`claude`) to be on PATH.
"""

import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from ragger.db import get_connection

# ---------------------------------------------------------------------------
# Tag taxonomy
# ---------------------------------------------------------------------------

CONTENT_CATEGORIES = {"quest", "skill", "minigame", "item", "npc", "location", "activity"}
FUNCTIONAL_CATEGORIES = {"progress", "toggle", "counter", "ui", "config", "storage", "timer", "cosmetic"}

VALID_SKILLS = [
    "attack", "strength", "defence", "ranged", "prayer", "magic", "runecraft",
    "construction", "hitpoints", "agility", "herblore", "thieving", "crafting",
    "fletching", "slayer", "hunter", "mining", "smithing", "fishing", "cooking",
    "firemaking", "woodcutting", "farming", "sailing",
]

# ---------------------------------------------------------------------------
# Known abbreviation map (prefix -> decoded meaning)
# Built from manual inspection of game_vars names and OSRS wiki quest/content names.
# The model doesn't HAVE to use only these, but should prefer them.
# ---------------------------------------------------------------------------

ABBREVIATIONS = {
    # Quests
    "GOBDIP": "quest:goblin_diplomacy",
    "HANDSAND": "quest:the_hand_in_the_sand",
    "PMOON": "quest:perilous_moons",
    "DS2": "quest:dragon_slayer_ii",
    "SOTE": "quest:song_of_the_elves",
    "MM": "quest:monkey_madness_i",
    "MM2": "quest:monkey_madness_ii",
    "MEP2": "quest:mournings_end_part_ii",
    "DT2": "quest:desert_treasure_ii",
    "RFD": "quest:recipe_for_disaster",
    "WGS": "quest:while_guthix_sleeps",
    "MOURNING": "quest:mournings_end_part_i",
    "ENAKH": "quest:enakhras_lament",
    "FORGET": "quest:forgettable_tale",
    "LOVAQUEST": "quest:a_kingdom_divided",
    "SLUG2": "quest:the_slug_menace",
    "SOTN": "quest:secrets_of_the_north",
    "ELEMENTAL": "quest:elemental_workshop_i",
    "LUNAR": "quest:lunar_diplomacy",
    "WANTED": "quest:wanted",
    "HORRORQUEST": "quest:horror_from_the_deep",
    "HORROR": "quest:horror_from_the_deep",
    "WATERFALL": "quest:waterfall_quest",
    "DEMONSLAYER": "quest:demon_slayer",
    "SHEEPHERDER": "quest:sheep_herder",
    "MYREQUE": "quest:in_aid_of_the_myreque",
    "VIKINGEXILE": "quest:the_fremennik_exiles",
    "VMQ3": "quest:the_path_of_glouphrie",
    "EYEGLO": "quest:the_eyes_of_glouphrie",
    "SHAYZIENQUEST": "quest:a_kingdom_divided",
    "ATJUN": "quest:at_first_light",
    "DOTI": "quest:death_on_the_isle",
    "TOL": "quest:tower_of_life",
    "HUNDRED": "quest:one_hundred_percent_favour",  # Kourend favour
    "KR": "quest:kings_ransom",
    "RESTLESS": "quest:the_restless_ghost",
    "MISC": "quest:throne_of_miscellania",
    "CAMDOZAAL": "quest:below_ice_mountain",
    "FD_TROLLCHILD": "quest:troll_romance",
    "TROLL": "quest:troll_stronghold",
    # Minigames / Activities
    "TOB": "minigame:theatre_of_blood",
    "TOA": "minigame:tombs_of_amascut",
    "COX": "minigame:chambers_of_xeric",
    "RAIDS": "minigame:chambers_of_xeric",
    "BA": "minigame:barbarian_assault",
    "BARBASSULT": "minigame:barbarian_assault",
    "NMZ": "minigame:nightmare_zone",
    "LMS": "minigame:last_man_standing",
    "GAUNTLET": "minigame:the_gauntlet",
    "HALLOWED": "minigame:hallowed_sepulchre",
    "COLOSSEUM": "minigame:fortis_colosseum",
    "GIANTS": "minigame:sleeping_giants",
    "BLAST": "minigame:blast_furnace",
    "SOUL": "minigame:soul_wars",
    "GIM": "activity:group_ironman",
    "DEADMAN": "activity:deadman_mode",
    "BOARDGAMES": "activity:board_games",
    "BINGO": "activity:bingo",
    "ENT": "activity:ent_totem_carving",
    "MOTHERLODE": "minigame:motherlode_mine",
    "MIXOLOGY": "minigame:herblore_mixology",
    "FORESTRY": "activity:forestry",
    # Activities / Systems
    "CA": "activity:combat_achievements",
    "LEAGUE": "activity:league",
    "COLLECTION": "activity:collection_log",
    "XPTRACKER": "activity:xp_tracker",
    "ADVENTUREPATH": "activity:adventure_path",
    "PVPA": "activity:pvp",
    "BR": "activity:pvp",
    "POLL": "activity:polls",
    "MUSIC": "activity:music",
    "FAIRYRINGS": "activity:fairy_rings",
    "FAIRYRING": "activity:fairy_rings",
    "PORT": "activity:ports",
    "FOSSIL": "activity:fossil_island",
    "HUNTING": "activity:hunter_rumours",
    "HW19": "activity:holiday_event",
    "HW20": "activity:holiday_event",
    "HW21": "activity:holiday_event",
    "HW22": "activity:holiday_event",
    "HH": "activity:holiday_event",
    "EASTER": "activity:holiday_event",
    "EASTER07": "activity:holiday_event",
    "PRIDE22": "activity:holiday_event",
    "PRIDE23": "activity:holiday_event",
    # Skills
    "POH": "skill:construction",
    "SLAYER": "skill:slayer",
    "SAILING": "skill:sailing",
    "FARMING": "skill:farming",
    # Locations
    "DORGESH": "location:dorgesh_kaan",
    "KELDAGRIM": "location:keldagrim",
    "PISCARILIUS": "location:piscarilius",
    # NPCs / Bosses
    "CORP": "npc:corporeal_beast",
    "MUSPAH": "npc:phantom_muspah",
    "KALPHITE": "npc:kalphite_queen",
    "JUVINATE": "npc:vyrewatch",
}


# ---------------------------------------------------------------------------
# Prompt construction (seeded with DB entity names)
# ---------------------------------------------------------------------------

def build_prompt(var_names: list[str], conn: sqlite3.Connection) -> str:
    """Build the classification prompt seeded with real entity names from the DB."""
    quest_names = sorted(
        r[0] for r in conn.execute("SELECT DISTINCT name FROM quests ORDER BY name").fetchall()
    )
    location_names = sorted(
        r[0] for r in conn.execute("SELECT DISTINCT name FROM locations ORDER BY name").fetchall()
    )
    # Bosses / notable NPCs: combat level > 100 or slayer category exists
    npc_names = sorted(set(
        r[0] for r in conn.execute(
            "SELECT DISTINCT name FROM monsters WHERE combat_level > 100 OR slayer_category IS NOT NULL ORDER BY name"
        ).fetchall()
    ))

    abbrev_lines = "\n".join(f"  {prefix} = {meaning}" for prefix, meaning in sorted(ABBREVIATIONS.items()))

    quest_list = ", ".join(quest_names)
    skill_list = ", ".join(VALID_SKILLS)
    location_list = ", ".join(location_names[:200])  # top 200 to keep prompt manageable
    npc_list = ", ".join(npc_names[:200])

    return f"""\
Classify these Old School RuneScape game variable names.

Variable names use UPPER_SNAKE_CASE with heavy abbreviation. A prefix usually identifies
the content area, and suffixes describe the specific property being tracked.

## Output format

Output ONLY a JSON array. No explanation, no markdown fences.

Each entry: {{"name": "VAR_NAME", "content": ["category:specific_name"], "functional": ["tag"]}}

## Content tags (category:specific_name)

Use snake_case for specific_name. Prefer names from the lists below. You may use names
not on these lists if you're confident, but strongly prefer known names.

**quest:<quest_name>** — which quest the var tracks
Known quests: {quest_list}

**skill:<skill_name>** — which skill
Known skills: {skill_list}

**npc:<npc_name>** — which NPC, boss, or monster
Known NPCs/bosses (partial list): {npc_list}

**location:<location_name>** — which location
Known locations (partial list): {location_list}

**item:<item_name>** — which item (too many to list; use your OSRS knowledge)

**minigame:<name>** — which minigame (e.g. theatre_of_blood, chambers_of_xeric, barbarian_assault, the_gauntlet, hallowed_sepulchre, tombs_of_amascut, motherlode_mine, blast_furnace, fortis_colosseum, last_man_standing, nightmare_zone, soul_wars, herblore_mixology, guardians_of_the_rift, pest_control, tithe_farm, volcanic_mine, wintertodt, tempoross, giants_foundry, mahogany_homes)

**activity:<name>** — broad game systems not covered above (e.g. combat_achievements, collection_log, league, xp_tracker, pvp, adventure_path, fairy_rings, fossil_island, music, holiday_event, polls, deadman_mode, group_ironman, ports, clans, diary)

## Functional tags

Values: progress, toggle, counter, ui, config, storage, timer, cosmetic

## Known abbreviations

These prefixes map to specific content. Apply them when you see the prefix:
{abbrev_lines}

## Rules

- A variable can have multiple content tags (e.g. a league task about a quest gets both activity:league and quest:X).
- If you can't determine content, use an empty array for content.
- LEAGUE_TASK_* = activity:league + whatever content the task name references.
- CA_TASK_* = activity:combat_achievements + the NPC/boss.
- COLLECTION_* = activity:collection_log + specific content if identifiable.
- XPTRACKER_* = activity:xp_tracker + the skill.
- SLAYER_* = skill:slayer + the NPC if identifiable.
- POH_* / POH_COS_* = skill:construction.
- MUSIC_* = activity:music.
- POTIONSTORE_* = activity:potionstore (NMZ potion storage).
- BUFF_* = track buff duration/state.

## Variables to classify

{chr(10).join(var_names)}"""


# ---------------------------------------------------------------------------
# Entity loading & validation
# ---------------------------------------------------------------------------

def build_entity_sets(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """Build sets of normalized entity names from the database for validation."""
    entities: dict[str, set[str]] = {}

    rows = conn.execute("SELECT DISTINCT name FROM quests").fetchall()
    entities["quest"] = {normalize(r[0]) for r in rows}

    rows = conn.execute("SELECT DISTINCT name FROM items").fetchall()
    entities["item"] = {normalize(r[0]) for r in rows}

    rows = conn.execute("SELECT DISTINCT name FROM monsters").fetchall()
    entities["npc"] = {normalize(r[0]) for r in rows}

    rows = conn.execute("SELECT DISTINCT name FROM npcs").fetchall()
    entities["npc"].update(normalize(r[0]) for r in rows)

    rows = conn.execute("SELECT DISTINCT name FROM locations").fetchall()
    entities["location"] = {normalize(r[0]) for r in rows}

    entities["skill"] = set(VALID_SKILLS)

    return entities


def normalize(name: str) -> str:
    """Normalize a name to snake_case for fuzzy matching."""
    s = name.lower()
    s = re.sub(r"[''']s\b", "s", s)  # possessives
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def validate_content_tags(
    tags: list[str], entities: dict[str, set[str]]
) -> tuple[list[str], list[str]]:
    """Validate content tags against DB entities. Returns (valid, flagged)."""
    valid = []
    flagged = []
    for tag in tags:
        if ":" not in tag:
            flagged.append(tag)
            continue
        category, value = tag.split(":", 1)
        if category not in CONTENT_CATEGORIES:
            flagged.append(tag)
            continue
        # activity and minigame don't have a DB table to validate against
        if category in ("activity", "minigame"):
            valid.append(tag)
            continue
        entity_set = entities.get(category)
        if entity_set is None:
            valid.append(tag)
            continue
        # Try exact match, then substring match against entity names
        norm_value = normalize(value)
        if norm_value in entity_set:
            valid.append(tag)
        elif any(norm_value in e or e in norm_value for e in entity_set if len(e) > 3):
            valid.append(tag)
        else:
            flagged.append(tag)
    return valid, flagged


# ---------------------------------------------------------------------------
# Claude CLI interaction
# ---------------------------------------------------------------------------

def classify_batch(
    var_names: list[str], model: str, claude_bin: str, conn: sqlite3.Connection
) -> list[dict]:
    """Send a batch of variable names to Claude via CLI."""
    prompt = build_prompt(var_names, conn)

    result = subprocess.run(
        [
            claude_bin,
            "--print",
            "--model", model,
            "--output-format", "text",
            "--system-prompt", "You classify OSRS game variable names. Output ONLY raw JSON — no markdown fences, no explanation, no preamble.",
            "--no-session-persistence",
            "--allowedTools", "",
        ],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=180,
    )

    if result.returncode != 0:
        print(f"  WARNING: claude exited with code {result.returncode}")
        print(f"  stderr: {result.stderr[:300]}")
        return []

    text = result.stdout.strip()

    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)

    # Try to extract a JSON array or object
    json_match = re.search(r"[\[{].*[\]}]", text, re.DOTALL)
    if not json_match:
        print(f"  WARNING: No JSON found in response:\n{text[:200]}")
        return []

    try:
        parsed = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        print(f"  WARNING: JSON decode error: {e}")
        print(f"  text: {text[:300]}")
        return []

    # Handle both {"vars": [...]} wrapper and bare [...] array
    if isinstance(parsed, dict):
        return parsed.get("vars", [])
    elif isinstance(parsed, list):
        return parsed
    return []


# ---------------------------------------------------------------------------
# DB writes
# ---------------------------------------------------------------------------

def write_tags(
    conn: sqlite3.Connection,
    var_name: str,
    var_type: str,
    content_tags: list[str],
    functional_tags: list[str],
) -> None:
    """Write classified tags back to the database."""
    conn.execute(
        "UPDATE game_vars SET content_tags = ?, functional_tags = ? WHERE name = ? AND var_type = ?",
        (
            json.dumps(content_tags) if content_tags else None,
            json.dumps(functional_tags) if functional_tags else None,
            var_name,
            var_type,
        ),
    )


def migrate_columns(conn: sqlite3.Connection) -> None:
    """Add tag columns if they don't exist (for existing databases)."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(game_vars)").fetchall()}
    if "content_tags" not in cols:
        conn.execute("ALTER TABLE game_vars ADD COLUMN content_tags TEXT")
    if "functional_tags" not in cols:
        conn.execute("ALTER TABLE game_vars ADD COLUMN functional_tags TEXT")
    conn.commit()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Classify game variable names with AI")
    parser.add_argument("--db", type=Path, default=Path("data/ragger.db"))
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--limit", type=int, default=None, help="Max vars to classify")
    parser.add_argument("--var-type", choices=["varp", "varbit", "varc_int", "varc_str"])
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--reclassify", action="store_true", help="Re-classify already tagged vars")
    parser.add_argument("--dry-run", action="store_true", help="Print tags without writing to DB")
    args = parser.parse_args()

    claude_bin = shutil.which("claude")
    if not claude_bin:
        print("Error: 'claude' CLI not found on PATH", file=sys.stderr)
        sys.exit(1)

    conn = get_connection(args.db)
    migrate_columns(conn)

    # Load unclassified vars
    query = "SELECT name, var_type FROM game_vars"
    params: list = []
    conditions = []
    if not args.reclassify:
        conditions.append("content_tags IS NULL AND functional_tags IS NULL")
    if args.var_type:
        conditions.append("var_type = ?")
        params.append(args.var_type)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY var_type, var_id"
    if args.limit:
        query += f" LIMIT {args.limit}"

    rows = conn.execute(query, params).fetchall()
    total = len(rows)
    if total == 0:
        print("No vars to classify.")
        return

    print(f"Classifying {total} vars in batches of {args.batch_size} using {args.model}")

    # Build validation entity sets
    entities = build_entity_sets(conn)
    print(f"Validation entities: {', '.join(f'{k}={len(v)}' for k, v in entities.items())}")

    classified = 0
    flagged_total = 0

    for batch_start in range(0, total, args.batch_size):
        batch = rows[batch_start : batch_start + args.batch_size]
        var_names = [r[0] for r in batch]
        var_types = {r[0]: r[1] for r in batch}
        batch_num = batch_start // args.batch_size + 1
        total_batches = (total + args.batch_size - 1) // args.batch_size

        print(f"\nBatch {batch_num}/{total_batches} ({len(batch)} vars)...")

        results = classify_batch(var_names, args.model, claude_bin, conn)

        # Index results by name
        result_map = {r["name"]: r for r in results if "name" in r}

        for var_name, var_type in batch:
            result = result_map.get(var_name)
            if not result:
                continue

            content_raw = result.get("content", [])
            functional_raw = result.get("functional", [])

            # Validate functional tags
            functional_tags = [t for t in functional_raw if t in FUNCTIONAL_CATEGORIES]

            # Validate content tags against DB
            valid_content, flagged_content = validate_content_tags(content_raw, entities)

            if args.dry_run:
                status = ""
                if flagged_content:
                    status = f"  FLAGGED: {flagged_content}"
                    flagged_total += len(flagged_content)
                print(f"  {var_name}: content={valid_content} functional={functional_tags}{status}")
            else:
                write_tags(conn, var_name, var_type, valid_content, functional_tags)
                classified += 1
                if flagged_content:
                    flagged_total += len(flagged_content)
                    print(f"  FLAGGED {var_name}: {flagged_content}")

        if not args.dry_run:
            conn.commit()

        # Rate limit between batches
        if batch_start + args.batch_size < total:
            time.sleep(0.5)

    if not args.dry_run:
        print(f"\nDone. Classified {classified} vars, {flagged_total} tags flagged and dropped.")
    else:
        print(f"\nDry run complete. {flagged_total} tags would be flagged.")

    conn.close()


if __name__ == "__main__":
    main()
