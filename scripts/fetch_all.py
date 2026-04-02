"""Run all fetch scripts in the correct order.

Order matters — items must be populated before quests or diary tasks,
since those scripts reference the items table. Linking scripts run last
since they depend on multiple tables being populated.
"""

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS = [
    # Core data (order matters)
    "scripts/fetch_items.py",
    "scripts/fetch_quests.py",
    "scripts/fetch_quest_regions.py",
    "scripts/fetch_diary_tasks.py",
    "scripts/fetch_diary_items.py",
    "scripts/fetch_shops.py",
    "scripts/fetch_locations.py",
    "scripts/fetch_facilities.py",
    "scripts/fetch_monsters.py",
    "scripts/fetch_map_links.py",
    # Linking passes (depend on multiple tables)
    "scripts/link_shop_locations.py",
    "scripts/link_facilities.py",
]


def run(db_path: Path, league_page: str | None = None) -> None:
    for script in SCRIPTS:
        print(f"\n=== {script} ===")
        result = subprocess.run(
            [sys.executable, script, "--db", str(db_path)],
            check=True,
        )

    if league_page:
        print(f"\n=== scripts/fetch_league_tasks.py ===")
        subprocess.run(
            [sys.executable, "scripts/fetch_league_tasks.py", "--db", str(db_path), "--page", league_page],
            check=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch all OSRS data into the database")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/clogger.db"),
        help="Path to the SQLite database",
    )
    parser.add_argument(
        "--league",
        default=None,
        help="Wiki page for league tasks (e.g. Raging_Echoes_League/Tasks)",
    )
    args = parser.parse_args()
    run(args.db, args.league)
