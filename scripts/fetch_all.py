"""Run all fetch scripts in the correct order.

Order matters — items must be populated before quests or diary tasks,
since those scripts reference the items table. Linking scripts run last
since they depend on multiple tables being populated.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from ragger.enums import League

SCRIPTS = [
    # Metadata (no dependencies)
    "scripts/pipeline/fetch_categories.py",
    # Core data (order matters)
    "scripts/pipeline/fetch_items.py",
    "scripts/pipeline/fetch_currencies.py",
    "scripts/pipeline/fetch_equipment.py",
    "scripts/pipeline/fetch_quests.py",
    "scripts/pipeline/fetch_quest_regions.py",
    "scripts/pipeline/fetch_diary_tasks.py",
    "scripts/pipeline/fetch_diary_items.py",
    "scripts/pipeline/fetch_shops.py",
    "scripts/pipeline/fetch_locations.py",
    "scripts/pipeline/fetch_facilities.py",
    "scripts/pipeline/fetch_monsters.py",
    "scripts/pipeline/fetch_dungeon_entrances.py",
    "scripts/pipeline/fetch_fairy_rings.py",
    "scripts/pipeline/fetch_quetzal.py",
    "scripts/pipeline/fetch_charter_ships.py",
    "scripts/pipeline/fetch_magic_teleports.py",
    "scripts/pipeline/fetch_activities.py",
    "scripts/pipeline/fetch_npcs.py",
    "scripts/pipeline/fetch_spells.py",
    "scripts/pipeline/fetch_ground_items.py",
    "scripts/pipeline/fetch_npc_locations.py",
    "scripts/pipeline/fetch_actions.py",
    "scripts/pipeline/fetch_wiki_vars.py",
    "scripts/pipeline/fetch_dialogues.py",
    # Category mapping (depends on all entity tables + wiki_categories)
    "scripts/pipeline/fetch_page_categories.py",
    # Linking / compute passes (depend on multiple tables)
    "scripts/pipeline/link_shop_locations.py",
    "scripts/pipeline/link_activity_locations.py",
    "scripts/pipeline/link_ground_item_locations.py",
    "scripts/pipeline/link_facilities.py",
    "scripts/pipeline/link_dialogue_entities.py",
    "scripts/pipeline/compute_dialogue_tags.py",
    "scripts/pipeline/compute_dialogue_instructions.py",
    "scripts/pipeline/link_npc_dialogues.py",
    "scripts/pipeline/link_quest_dialogues.py",
    "scripts/pipeline/compute_blobs.py",
    "scripts/pipeline/compute_gate_links.py",
    "scripts/pipeline/compute_ports.py",
    "scripts/pipeline/compute_port_transits.py",
    "scripts/pipeline/compute_port_crossings.py",
    "scripts/pipeline/compute_map_link_blobs.py",
]


def run(db_path: Path, league: str | None = None) -> None:
    for script in SCRIPTS:
        print(f"\n=== {script} ===")
        result = subprocess.run(
            [sys.executable, script, "--db", str(db_path)],
            check=True,
        )

    if league:
        print(f"\n=== scripts/pipeline/fetch_league_tasks.py ===")
        subprocess.run(
            [sys.executable, "scripts/pipeline/fetch_league_tasks.py",
             "--db", str(db_path), "--league", league],
            check=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch all OSRS data into the database")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/ragger.db"),
        help="Path to the SQLite database",
    )
    parser.add_argument(
        "--league",
        default=None,
        choices=[l.name for l in League],
        help="Which league to ingest tasks for (e.g. DEMONIC_PACTS).",
    )
    args = parser.parse_args()
    run(args.db, args.league)
