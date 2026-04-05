"""Classify game variable names using the Claude CLI and validate against the database.

Uses Claude CLI in --print mode with the taxonomy as a system prompt and seed examples
in the user message. Each batch is an independent call with --no-session-persistence.
Supports parallel workers for throughput.

Requires the Claude CLI (`claude`) to be on PATH.
"""

import argparse
import json
import queue
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ragger.db import get_connection
from ragger.enums import ContentCategory, FunctionalTag, Skill

# ---------------------------------------------------------------------------
# Tag taxonomy (derived from enums)
# ---------------------------------------------------------------------------

CONTENT_CATEGORIES = {c.value for c in ContentCategory}
FUNCTIONAL_CATEGORIES = {f.value for f in FunctionalTag}

VALID_SKILLS = [s.label.lower() for s in Skill] + ["sailing"]

# System-level activity names that don't come from the activities table
SYSTEM_ACTIVITIES = {
    "combat_achievements", "collection_log", "league", "league_tasks",
    "xp_tracker", "pvp", "adventure_path", "fairy_rings", "fossil_island",
    "music", "holiday_event", "polls", "deadman_mode", "group_ironman",
    "ports", "clans", "diary", "potionstore", "board_games",
    "hunter_rumours", "ent_totem_carving",
}

# ---------------------------------------------------------------------------
# Known abbreviation map (prefix -> decoded meaning)
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
    "HUNDRED": "quest:one_hundred_percent_favour",
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
# Seed batch — synthetic examples covering all categories and tag combos
# ---------------------------------------------------------------------------

SEED_EXPECTED = """\
GOBDIP_STATE | quest:goblin_diplomacy | progress
DS2_VORKATH_DEFEATED | quest:dragon_slayer_ii, npc:vorkath | progress
SOTE_FRAGMENT_COLLECTED | quest:song_of_the_elves | progress
SLAYER_TASK_AMOUNT | skill:slayer | counter
FARMING_PATCH_RAKED | skill:farming | toggle
SAILING_VOYAGE_COUNT | skill:sailing | counter
CORP_KILL_COUNT | npc:corporeal_beast | counter
KALPHITE_QUEEN_FORM | npc:kalphite_queen | toggle
DORGESH_KAAN_VISITED | location:dorgesh_kaan | toggle
KELDAGRIM_TRAIN_UNLOCKED | location:keldagrim | toggle
LOOTING_BAG_STORED_ITEMS | item:looting_bag | storage
TOB_COMPLETION_COUNT | minigame:theatre_of_blood | counter
BA_QUEEN_KILLS | minigame:barbarian_assault | counter
COX_TOTAL_POINTS | minigame:chambers_of_xeric | counter
MUSIC_TRACK_UNLOCKED_042 | activity:music | toggle
COLLECTION_LOG_ABYSSAL_WHIP | activity:collection_log, item:abyssal_whip | toggle
XPTRACKER_MINING_GAINED | activity:xp_tracker, skill:mining | counter
LEAGUE_TASK_COMPLETE_MM2 | activity:league, quest:monkey_madness_ii | toggle
CA_TASK_GIANT_MOLE | activity:combat_achievements, npc:giant_mole | toggle
SLAYER_KRAKEN_KILLS | skill:slayer, npc:cave_kraken | counter
COM_STANCE | - | config
CHATBOX_INPUT_TYPE | - | ui
SIDE_PANEL_TAB | - | ui
BUFF_ANTIFIRE_TIMER | item:antifire_potion | timer
BUFF_PRAYER_RENEWAL | item:prayer_renewal | timer
BRIGHTNESS_SETTING | - | config
ROOFS_HIDDEN | - | config
POH_COS_WALLPAPER_STYLE | skill:construction | cosmetic
AAAA_BBBB_CCCC | - | -"""


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def build_system_prompt(conn: sqlite3.Connection) -> str:
    """Build the system prompt with taxonomy and entity lists. Reused across all calls."""
    quest_names = sorted(
        r[0] for r in conn.execute("SELECT DISTINCT name FROM quests ORDER BY name").fetchall()
    )
    location_names = sorted(
        r[0] for r in conn.execute("SELECT DISTINCT name FROM locations ORDER BY name").fetchall()
    )
    npc_names = sorted(set(
        r[0] for r in conn.execute(
            "SELECT DISTINCT name FROM monsters WHERE combat_level > 100 OR slayer_category IS NOT NULL ORDER BY name"
        ).fetchall()
    ))
    minigame_names = sorted(
        r[0] for r in conn.execute(
            "SELECT DISTINCT name FROM activities WHERE type IN ('Minigame', 'Raid') ORDER BY name"
        ).fetchall()
    )
    activity_names = sorted(
        r[0] for r in conn.execute(
            "SELECT DISTINCT name FROM activities WHERE type NOT IN ('Minigame', 'Raid', 'Random event') ORDER BY name"
        ).fetchall()
    )

    abbrev_lines = "\n".join(f"  {prefix} = {meaning}" for prefix, meaning in sorted(ABBREVIATIONS.items()))

    return f"""\
You are a classifier for Old School RuneScape game variable names.

Variable names use UPPER_SNAKE_CASE with heavy abbreviation. A prefix usually identifies
the content area, and suffixes describe the specific property being tracked.

## Output format

One line per variable, exactly:
VAR_NAME | content_tag1, content_tag2 | functional_tag1, functional_tag2

Use - for empty columns. No explanation. No headers. Just the lines.

## Content tags (category:specific_name)

Use snake_case for specific_name. Prefer names from the lists below.

quest: {", ".join(quest_names)}
skill: {", ".join(VALID_SKILLS)}
npc (partial): {", ".join(npc_names[:200])}
location (partial): {", ".join(location_names[:200])}
item: use your OSRS knowledge
minigame: {", ".join(minigame_names)}
activity: {", ".join(activity_names)}
Also: combat_achievements, collection_log, league, xp_tracker, pvp, adventure_path, fairy_rings, fossil_island, music, holiday_event, polls, deadman_mode, group_ironman, ports, clans, diary

## Functional tags

progress, toggle, counter, ui, config, storage, timer, cosmetic

## Known abbreviations

{abbrev_lines}

## Rules

- Multiple content tags OK (e.g. league task about a quest = activity:league, quest:X)
- LEAGUE_TASK_* = activity:league + referenced content
- CA_TASK_* = activity:combat_achievements + NPC/boss
- COLLECTION_* = activity:collection_log + specific content if identifiable
- XPTRACKER_* = activity:xp_tracker + skill
- SLAYER_* = skill:slayer + NPC if identifiable
- POH_* / POH_COS_* = skill:construction
- MUSIC_* = activity:music
- POTIONSTORE_* = activity:potionstore
- BUFF_* = timer"""


def build_user_message(var_names: list[str]) -> str:
    """Build the user message with seed examples and variables to classify."""
    return f"Here is an example of correct classification:\n\n{SEED_EXPECTED}\n\nNow classify these:\n" + "\n".join(var_names)


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

    rows = conn.execute("SELECT DISTINCT name, type FROM activities").fetchall()
    entities["minigame"] = {normalize(r[0]) for r in rows if r[1] in ("Minigame", "Raid")}
    entities["activity"] = {normalize(r[0]) for r in rows if r[1] not in ("Minigame", "Raid", "Random event")}
    entities["activity"].update(SYSTEM_ACTIVITIES)

    entities["skill"] = set(VALID_SKILLS)

    return entities


def normalize(name: str) -> str:
    """Normalize a name to snake_case for fuzzy matching."""
    s = name.lower()
    s = re.sub(r"[''']s\b", "s", s)
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
        entity_set = entities.get(category)
        if entity_set is None:
            valid.append(tag)
            continue
        norm_value = normalize(value)
        stripped_value = norm_value.replace("_", "")
        if norm_value in entity_set:
            valid.append(tag)
        elif any(stripped_value == e.replace("_", "") for e in entity_set):
            valid.append(tag)
        elif any(norm_value in e or e in norm_value for e in entity_set if len(e) > 3):
            valid.append(tag)
        else:
            flagged.append(tag)
    return valid, flagged


# ---------------------------------------------------------------------------
# Claude CLI interaction
# ---------------------------------------------------------------------------

def parse_response(text: str, var_set: set[str]) -> list[dict]:
    """Parse pipe-delimited response lines into result dicts."""
    results = []
    for line in text.splitlines():
        line = line.strip()
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue

        name = parts[0]
        if name not in var_set:
            continue

        content_str = parts[1] if len(parts) > 1 else "-"
        functional_str = parts[2] if len(parts) > 2 else "-"

        content = [t.strip() for t in content_str.split(",") if t.strip() and t.strip() != "-"]
        functional = [t.strip() for t in functional_str.split(",") if t.strip() and t.strip() != "-"]

        results.append({"name": name, "content": content, "functional": functional})

    return results


def classify_batch(
    var_names: list[str],
    system_prompt: str,
    claude_bin: str,
    model: str,
    session_id: str | None = None,
    first_session_id: str | None = None,
    timeout: int = 300,
) -> list[dict]:
    """Classify a batch of variable names via --print.

    If session_id is given, resumes that session (taxonomy already loaded).
    If first_session_id is given, creates a new session with that ID.
    """
    user_msg = build_user_message(var_names)

    cmd = [
        claude_bin,
        "--print",
        "--model", model,
        "--output-format", "text",
        "--allowedTools", "",
    ]

    if session_id:
        # Resume existing session — taxonomy already loaded
        cmd.extend(["--resume", session_id])
        input_msg = "Classify these:\n" + "\n".join(var_names)
    else:
        # First call — send full taxonomy + seed examples
        cmd.extend(["--system-prompt", system_prompt])
        if first_session_id:
            cmd.extend(["--session-id", first_session_id])
        input_msg = user_msg

    result = subprocess.run(
        cmd,
        input=input_msg,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        return [], result.stdout, result.stderr

    return parse_response(result.stdout, set(var_names)), result.stdout, result.stderr


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
# Progress display
# ---------------------------------------------------------------------------

class Progress:
    """Thread-safe progress tracker."""

    def __init__(self, total: int, enabled: bool = True):
        self.total = total
        self.done = 0
        self.flagged = 0
        self.failed = 0
        self.enabled = enabled
        self._lock = threading.Lock()
        self._start = time.time()

    def update(self, classified: int, flagged: int = 0, failed: int = 0) -> None:
        with self._lock:
            self.done += classified
            self.flagged += flagged
            self.failed += failed
            if self.enabled:
                self._render()

    def _render(self) -> None:
        elapsed = time.time() - self._start
        pct = self.done / self.total * 100 if self.total else 0
        rate = self.done / elapsed if elapsed > 0 else 0
        eta = (self.total - self.done) / rate if rate > 0 else 0

        bar_width = 30
        filled = int(bar_width * self.done / self.total) if self.total else 0
        bar = "█" * filled + "░" * (bar_width - filled)

        parts = [f"\r{bar} {pct:5.1f}% {self.done}/{self.total}"]
        parts.append(f" ({rate:.0f}/s, ETA {eta:.0f}s)")
        if self.flagged:
            parts.append(f" [{self.flagged} flagged]")
        if self.failed:
            parts.append(f" [{self.failed} failed]")

        sys.stderr.write("".join(parts))
        sys.stderr.flush()

    def finish(self) -> None:
        if self.enabled:
            self._render()
            sys.stderr.write("\n")
            sys.stderr.flush()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Classify game variable names with AI")
    parser.add_argument("--db", type=Path, default=Path("data/ragger.db"))
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--limit", type=int, default=None, help="Max vars to classify")
    parser.add_argument("--var-type", choices=["varp", "varbit", "varc_int", "varc_str"])
    parser.add_argument("--model", default="opus")
    parser.add_argument("--workers", type=int, default=1, help="Parallel workers")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout per batch in seconds")
    parser.add_argument("--delay", type=int, default=10, help="Seconds between batches per worker")
    parser.add_argument("--session-reset", type=int, default=5, dest="session_reset",
                        help="Reset session every N batches to limit context growth (default: 5)")
    parser.add_argument("--reclassify", action="store_true", help="Re-classify already tagged vars")
    parser.add_argument("--dry-run", action="store_true", help="Print tags without writing to DB")
    parser.add_argument("--progress", action=argparse.BooleanOptionalAction, default=True,
                        help="Show progress bar (default: on)")
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

    total_batches = (total + args.batch_size - 1) // args.batch_size
    print(f"Classifying {total} vars in {total_batches} batches of {args.batch_size} "
          f"using {args.model} with {args.workers} worker(s)", flush=True)

    # Build system prompt and validation sets
    system_prompt = build_system_prompt(conn)
    entities = build_entity_sets(conn)

    # Split into batches
    batches = []
    for i in range(0, total, args.batch_size):
        batch_rows = rows[i : i + args.batch_size]
        batches.append(batch_rows)

    progress = Progress(total, enabled=args.progress)

    # DB writer queue — all DB ops happen on the writer thread
    write_queue: queue.Queue = queue.Queue()
    SENTINEL = "STOP"
    COMMIT = "COMMIT"

    def db_writer() -> None:
        writer_conn = sqlite3.connect(args.db)
        writer_conn.execute("PRAGMA foreign_keys = ON")
        while True:
            item = write_queue.get()
            if item is SENTINEL:
                writer_conn.commit()
                writer_conn.close()
                write_queue.task_done()
                break
            if item is COMMIT:
                writer_conn.commit()
                write_queue.task_done()
                continue
            var_name, var_type, content_tags, functional_tags = item
            write_tags(writer_conn, var_name, var_type, content_tags, functional_tags)
            write_queue.task_done()

    writer_thread = threading.Thread(target=db_writer, daemon=True)
    if not args.dry_run:
        writer_thread.start()

    def worker_loop(worker_batches: list[list[tuple]], worker_id: int) -> None:
        session_id = str(uuid.uuid4())
        session_batch_count = 0

        for i, batch_rows in enumerate(worker_batches):
            if i > 0:
                time.sleep(args.delay)

            # Reset session every N batches to keep context window small
            if session_batch_count >= args.session_reset:
                session_id = str(uuid.uuid4())
                session_batch_count = 0

            var_names = [r[0] for r in batch_rows]
            var_types = {r[0]: r[1] for r in batch_rows}

            t0 = time.time()
            is_fresh = session_batch_count == 0
            try:
                results, raw_stdout, raw_stderr = classify_batch(
                    var_names, system_prompt, claude_bin, args.model,
                    session_id=session_id if not is_fresh else None,
                    timeout=args.timeout,
                    first_session_id=session_id if is_fresh else None,
                )
            except subprocess.TimeoutExpired:
                ttr = time.time() - t0
                print(f"  W{worker_id}B{i}: TIMEOUT after {ttr:.1f}s", file=sys.stderr, flush=True)
                progress.update(0, failed=len(var_names))
                continue
            ttr = time.time() - t0

            # Log any stderr from the CLI
            if raw_stderr.strip():
                print(f"  W{worker_id}B{i}: stderr: {raw_stderr.strip()[:200]}", file=sys.stderr, flush=True)

            # Check if output has non-pipe content (thinking, tool use, etc.)
            non_pipe_lines = [l for l in raw_stdout.splitlines() if l.strip() and "|" not in l]
            if non_pipe_lines:
                print(f"  W{worker_id}B{i}: extra output: {non_pipe_lines[:3]}", file=sys.stderr, flush=True)

            result_map = {r["name"]: r for r in results}
            batch_flagged = 0

            for var_name, var_type in batch_rows:
                result = result_map.get(var_name)
                if not result:
                    continue

                content_raw = result.get("content", [])
                functional_raw = result.get("functional", [])

                functional_tags = [t for t in functional_raw if t in FUNCTIONAL_CATEGORIES]
                valid_content, flagged_content = validate_content_tags(content_raw, entities)
                batch_flagged += len(flagged_content)

                if not args.dry_run:
                    write_queue.put((var_name, var_type, valid_content, functional_tags))

            # Flush writes after each batch
            if not args.dry_run:
                write_queue.put(COMMIT)
                write_queue.join()

            session_batch_count += 1
            resumed = "resume" if not is_fresh else "new"
            print(f"  W{worker_id}B{i}: TTR={ttr:.1f}s parsed={len(result_map)}/{len(batch_rows)} ({resumed})",
                  file=sys.stderr, flush=True)

            progress.update(len(batch_rows), flagged=batch_flagged,
                            failed=len(batch_rows) - len(result_map))

    # Distribute batches round-robin to workers
    worker_assignments: list[list[list[tuple]]] = [[] for _ in range(args.workers)]
    for i, batch in enumerate(batches):
        worker_assignments[i % args.workers].append(batch)

    if args.workers > 1:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(worker_loop, wa, i) for i, wa in enumerate(worker_assignments)]
            for f in as_completed(futures):
                f.result()
    else:
        worker_loop(worker_assignments[0], 0)

    # Stop writer thread
    if not args.dry_run:
        write_queue.put(SENTINEL)
        write_queue.join()
        writer_thread.join()

    progress.finish()

    elapsed = time.time() - progress._start
    print(f"\nDone in {elapsed:.1f}s. "
          f"Classified: {progress.done}, flagged: {progress.flagged}, failed: {progress.failed}")

    conn.close()


if __name__ == "__main__":
    main()
