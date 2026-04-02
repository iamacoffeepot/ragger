"""Create a GitHub release with the database attached.

Tags the current commit and uploads data/clogger.db as a release asset.
Generates attribution credits from the attributions table in the database.

Usage:
    uv run python scripts/release.py v0.1.0
    uv run python scripts/release.py v0.1.0 --notes "Initial data with Raging Echoes tasks"
"""

import argparse
import sqlite3
import subprocess
import sys
from pathlib import Path

DB_PATH = Path("data/clogger.db")
VERSION_PATH = Path("VERSION")
CREDITS_PATH = Path("CREDITS.md")


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def generate_credits(db_path: Path) -> str:
    """Generate attribution credits from the database."""
    conn = sqlite3.connect(db_path)

    rows = conn.execute(
        "SELECT table_name, wiki_page, authors FROM attributions ORDER BY table_name, wiki_page"
    ).fetchall()
    conn.close()

    if not rows:
        return ""

    # Collect unique authors across all pages
    all_authors: set[str] = set()
    pages_by_table: dict[str, list[str]] = {}
    for table_name, wiki_page, authors in rows:
        pages_by_table.setdefault(table_name, []).append(wiki_page)
        if authors:
            for author in authors.split(", "):
                author = author.strip()
                if author and author != "Category contributors":
                    all_authors.add(author)

    lines: list[str] = []
    lines.append("# Data Attribution")
    lines.append("")
    lines.append("All data sourced from the [Old School RuneScape Wiki](https://oldschool.runescape.wiki/),")
    lines.append("licensed under [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/).")
    lines.append("")
    lines.append("## Sources")
    lines.append("")

    # Group by table, show page links with contributors
    authors_by_page: dict[str, str] = {}
    for _, wiki_page, authors in rows:
        if authors:
            authors_by_page[wiki_page] = authors

    for table_name, pages in sorted(pages_by_table.items()):
        lines.append(f"### {table_name}")
        lines.append("")
        for page in sorted(set(pages)):
            url = f"https://oldschool.runescape.wiki/w/{page.replace(' ', '_')}"
            lines.append(f"- [{page}]({url})")
            authors = authors_by_page.get(page)
            if authors:
                lines.append(f"  Contributors: {authors}")
        lines.append("")

    return "\n".join(lines)


def release(version: str, notes: str) -> None:
    if not DB_PATH.exists():
        print(f"Error: {DB_PATH} not found. Run fetch_all.py first.")
        sys.exit(1)

    size_mb = DB_PATH.stat().st_size / (1024 * 1024)
    print(f"Database: {DB_PATH} ({size_mb:.1f} MB)")

    # Generate credits
    credits = generate_credits(DB_PATH)
    if credits:
        CREDITS_PATH.write_text(credits)
        print(f"Generated {CREDITS_PATH} ({len(credits)} chars)")

    # Tag the commit
    result = run(["git", "tag", version], check=False)
    if result.returncode != 0:
        if "already exists" in result.stderr:
            print(f"Tag {version} already exists. Use a new version.")
            sys.exit(1)
        print(f"Error tagging: {result.stderr}")
        sys.exit(1)
    print(f"Tagged {version}")

    # Push the tag
    run(["git", "push", "origin", version])
    print(f"Pushed tag {version}")

    # Build release assets
    assets = [str(DB_PATH)]
    if CREDITS_PATH.exists():
        assets.append(str(CREDITS_PATH))

    # Build release notes with attribution summary
    full_notes = notes
    if credits:
        conn = sqlite3.connect(DB_PATH)
        author_count = len(set(
            a.strip()
            for row in conn.execute("SELECT authors FROM attributions").fetchall()
            if row[0]
            for a in row[0].split(", ")
            if a.strip() and a.strip() != "Category contributors"
        ))
        page_count = conn.execute("SELECT COUNT(DISTINCT wiki_page) FROM attributions").fetchone()[0]
        conn.close()
        full_notes += f"\n\nData sourced from {page_count} [OSRS Wiki](https://oldschool.runescape.wiki/) pages by {author_count} contributors. See CREDITS.md for full attribution."

    # Create the release
    cmd = [
        "gh", "release", "create", version,
        *assets,
        "--title", version,
        "--notes", full_notes,
    ]
    result = run(cmd)
    print(f"Release created: {result.stdout.strip()}")


if __name__ == "__main__":
    default_version = "v" + VERSION_PATH.read_text().strip() if VERSION_PATH.exists() else None
    parser = argparse.ArgumentParser(description="Create a GitHub release with the database")
    parser.add_argument("version", nargs="?", default=default_version, help="Version tag (e.g. v0.1.0, defaults to VERSION file)")
    parser.add_argument(
        "--notes",
        default="Database release",
        help="Release notes",
    )
    args = parser.parse_args()
    release(args.version, args.notes)
