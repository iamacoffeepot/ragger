"""Classify game variable names using Claude CLI (Haiku) and validate against the database.

Sends batches of variable names to Claude Haiku via the `claude` CLI for
content/functional tag classification, then validates content tags against
real entity names in the quests, monsters, locations, items, and NPCs tables.

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

VALID_SKILLS = {
    "attack", "strength", "defence", "ranged", "prayer", "magic", "runecraft",
    "construction", "hitpoints", "agility", "herblore", "thieving", "crafting",
    "fletching", "slayer", "hunter", "mining", "smithing", "fishing", "cooking",
    "firemaking", "woodcutting", "farming", "sailing",
}

CLASSIFICATION_PROMPT = """\
You are classifying Old School RuneScape game variable names. Each variable has a NAME \
that encodes what it tracks using abbreviated conventions.

For each variable, output:
1. **content**: What game content the variable relates to. Format: `category:specific_name`
   Categories: quest, skill, minigame, item, npc, location, activity
   Use snake_case for specific names. Decode abbreviations (e.g. GOBDIP = Goblin Diplomacy, \
HANDSAND = Hand in the Sand, PMOON = Perilous Moons, DS2 = Dragon Slayer II, SOTE = Song of the Elves, \
MM2 = Monkey Madness II, MEP2 = Mourning's End Part II, DT2 = Desert Treasure II, \
RFD = Recipe for Disaster, TOB = Theatre of Blood, TOA = Tombs of Amascut, COX = Chambers of Xeric, \
BA = Barbarian Assault, NMZ = Nightmare Zone, LMS = Last Man Standing, GWD = God Wars Dungeon, \
ZULR = Zulrah, JADSIM = TzHaar Fight Cave, INFERNO = The Inferno, GAUNTLET = The Gauntlet).
   A variable can have multiple content tags if it relates to multiple things.
   Use "activity" for broad systems (collection_log, combat_achievements, league_tasks, pvp, xp_tracker, etc.).

2. **functional**: What the variable does mechanically.
   Values: progress, toggle, counter, ui, config, storage, timer, cosmetic
   A variable can have multiple functional tags.

Rules:
- If you can't determine a content tag, use an empty array.
- Prefer specific entity names over generic categories.
- SAILING_* vars are skill:sailing (it's an official skill).
- LEAGUE_TASK_* vars are activity:league_tasks plus whatever content they reference.
- CA_TASK_* vars are activity:combat_achievements plus the NPC/boss they reference.
- COLLECTION_* vars are activity:collection_log plus specific content if identifiable.
- XPTRACKER_* vars are activity:xp_tracker plus the skill.
- MUSIC_* vars are activity:music.
- POH_* vars are skill:construction.
- SLAYER_* vars are skill:slayer plus the NPC if identifiable.
- HW19/HW20/HW21/HW22 = Halloween event years. Tag as activity:holiday_event.
- FOSSIL_* = activity:fossil_island (Fossil Island activities).
- BR_LOADOUT/PVPA_* = activity:pvp.
- FAIRYRINGS_* = activity:fairy_rings.
- PORT_* = activity:ports.
- DORGESH_* = location:dorgesh_kaan.

Here are the variables to classify:
"""


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

    entities["skill"] = VALID_SKILLS

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


def classify_batch(var_names: list[str], model: str, claude_bin: str) -> list[dict]:
    """Send a batch of variable names to Haiku via Claude CLI."""
    names_text = "\n".join(var_names)
    prompt = CLASSIFICATION_PROMPT + names_text

    result = subprocess.run(
        [
            claude_bin,
            "--print",
            "--model", model,
            "--output-format", "text",
            "--system-prompt", "You classify OSRS game variable names. Output ONLY raw JSON, no markdown fences, no explanation.",
            "--no-session-persistence",
            "--allowedTools", "",
        ],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=120,
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify game variable names with AI")
    parser.add_argument("--db", type=Path, default=Path("data/ragger.db"))
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--limit", type=int, default=None, help="Max vars to classify")
    parser.add_argument("--var-type", choices=["varp", "varbit", "varc_int", "varc_str"])
    parser.add_argument("--model", default="haiku")
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

    print(f"Classifying {total} vars in batches of {args.batch_size}")

    # Build validation entity sets
    entities = build_entity_sets(conn)
    print(f"Loaded validation entities: {', '.join(f'{k}={len(v)}' for k, v in entities.items())}")

    classified = 0
    flagged_total = 0

    for batch_start in range(0, total, args.batch_size):
        batch = rows[batch_start : batch_start + args.batch_size]
        var_names = [r[0] for r in batch]
        var_types = {r[0]: r[1] for r in batch}
        batch_num = batch_start // args.batch_size + 1
        total_batches = (total + args.batch_size - 1) // args.batch_size

        print(f"\nBatch {batch_num}/{total_batches} ({len(batch)} vars)...")

        results = classify_batch(var_names, args.model, claude_bin)

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
