"""Import map square images into the database.

Supports two sources:
  - Cache dump directory (data/cache-dump/) with collision, water, and map-tiles subdirs
  - Legacy zip file (data/map-squares.zip) with {plane}_{rx}_{ry}.png files

Usage:
    uv run python scripts/import_map_squares.py [--db data/clogger.db]
    uv run python scripts/import_map_squares.py --zip data/map-squares.zip
"""

import argparse
import re
import zipfile
from pathlib import Path

from clogger.db import create_tables, get_connection
from clogger.enums import MapSquareType

TILE_PATTERN = re.compile(r"(\d+)_(\d+)_(\d+)\.png")

TYPE_DIRS = {
    MapSquareType.COLLISION: "collision",
    MapSquareType.WATER: "water",
    MapSquareType.COLOR: "map-tiles",
}


def import_from_cache_dump(db_path: Path, dump_dir: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    total = 0
    for sq_type, subdir in TYPE_DIRS.items():
        tile_dir = dump_dir / subdir
        if not tile_dir.is_dir():
            print(f"  Skipping {sq_type.value}: {tile_dir} not found")
            continue

        count = 0
        for png in tile_dir.glob("*.png"):
            m = TILE_PATTERN.match(png.name)
            if not m:
                continue
            plane = int(m.group(1))
            region_x = int(m.group(2))
            region_y = int(m.group(3))
            image = png.read_bytes()

            conn.execute(
                "INSERT OR REPLACE INTO map_squares (plane, region_x, region_y, type, image) VALUES (?, ?, ?, ?, ?)",
                (plane, region_x, region_y, sq_type.value, image),
            )
            count += 1

        print(f"  {sq_type.value}: {count} tiles")
        total += count

    conn.commit()
    print(f"Imported {total} map squares into {db_path}")
    conn.close()


def import_from_zip(db_path: Path, zip_path: Path) -> None:
    if not zip_path.exists():
        print(f"Error: {zip_path} not found.")
        return

    create_tables(db_path)
    conn = get_connection(db_path)

    count = 0
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            m = TILE_PATTERN.match(name)
            if not m:
                continue
            plane = int(m.group(1))
            region_x = int(m.group(2))
            region_y = int(m.group(3))
            image = zf.read(name)

            conn.execute(
                "INSERT OR REPLACE INTO map_squares (plane, region_x, region_y, type, image) VALUES (?, ?, ?, ?, ?)",
                (plane, region_x, region_y, MapSquareType.COLOR.value, image),
            )
            count += 1

    conn.commit()
    print(f"Imported {count} map squares (color) into {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import map squares into database")
    parser.add_argument("--db", type=Path, default=Path("data/clogger.db"))
    parser.add_argument("--zip", type=Path, default=None, help="Legacy zip file path")
    parser.add_argument("--dump-dir", type=Path, default=Path("data/cache-dump"), help="Cache dump directory")
    args = parser.parse_args()

    if args.zip:
        import_from_zip(args.db, args.zip)
    else:
        import_from_cache_dump(args.db, args.dump_dir)
