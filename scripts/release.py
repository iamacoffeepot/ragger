"""Create a GitHub release with the database attached.

Tags the current commit and uploads data/clogger.db as a release asset.

Usage:
    uv run python scripts/release.py v0.1.0
    uv run python scripts/release.py v0.1.0 --notes "Initial data with Raging Echoes tasks"
"""

import argparse
import subprocess
import sys
from pathlib import Path

DB_PATH = Path("data/clogger.db")
VERSION_PATH = Path("VERSION")


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def release(version: str, notes: str) -> None:
    if not DB_PATH.exists():
        print(f"Error: {DB_PATH} not found. Run fetch_all.py first.")
        sys.exit(1)

    size_mb = DB_PATH.stat().st_size / (1024 * 1024)
    print(f"Database: {DB_PATH} ({size_mb:.1f} MB)")

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

    # Create the release with the database attached
    cmd = [
        "gh", "release", "create", version,
        str(DB_PATH),
        "--title", version,
        "--notes", notes,
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
