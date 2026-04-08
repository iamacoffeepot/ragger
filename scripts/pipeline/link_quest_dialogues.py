"""Link quests to dialogue pages by matching quest names to transcript titles."""

import argparse
from pathlib import Path

from ragger.db import create_tables, get_connection


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    conn.execute("DELETE FROM quest_dialogues")

    linked = conn.execute(
        """INSERT OR IGNORE INTO quest_dialogues (quest_id, page_id)
           SELECT q.id, dp.id
           FROM quests q
           JOIN dialogue_pages dp ON dp.title = q.name
           WHERE dp.page_type = 'quest'""",
    ).rowcount

    conn.commit()
    print(f"Linked {linked} quest-dialogue pairs", flush=True)
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Link quests to dialogue pages")
    parser.add_argument("--db", type=Path, default=Path("data/ragger.db"))
    args = parser.parse_args()
    ingest(args.db)
