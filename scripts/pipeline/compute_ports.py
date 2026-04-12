"""Compute ports: crossing points along Voronoi ridges, grouped by blob.

For each Voronoi ridge separating two cells A and B, we sample points along
the ridge segment and look up the walkable blob on each side. Contiguous
samples that share the same (blob_A, blob_B) pair collapse into one port pair
— one row per side, linking the ridge to the blob it touches on that side.

Ports are the graph nodes for precise cross-cell pathfinding: walking from one
side of a ridge to the other is a free transition between paired ports;
moving between two ports inside the same cell costs a BFS distance through
their shared blob.

Requires: `compute_blobs.py` to have been run first (reads from
MapSquareType.BLOB map squares and the blobs table).
"""

import argparse
from pathlib import Path

import numpy as np
from scipy.spatial import Voronoi

from ragger.db import create_tables, get_connection
from ragger.map import GAME_TILES_PER_REGION, MapSquare

Y_WORLD_SPLIT = 5000  # overworld < 5000 <= underworld (matches compute_blobs)
DEFAULT_EDGE_SAMPLES = 128
MAX_SIDE_OFFSET = 6  # tiles to scan away from the ridge while resolving a side blob


def lookup_blob_side(
    blob_grid: np.ndarray,
    extent: tuple[int, int, int, int],
    sample_x: float,
    sample_y: float,
    dir_x: float,
    dir_y: float,
    max_offset: int = MAX_SIDE_OFFSET,
) -> tuple[int, int, int]:
    """Step from the sample in (dir_x, dir_y) looking for the first walkable
    tile. Returns (blob_id, resolved_gx, resolved_gy). blob_id=0 if nothing
    walkable is found within `max_offset` tiles.
    """
    x_min, _x_max, _y_min, y_max = extent
    H, W = blob_grid.shape
    for step in range(1, max_offset + 1):
        gx = int(round(sample_x + dir_x * step))
        gy = int(round(sample_y + dir_y * step))
        px = gx - x_min
        py = y_max - 1 - gy
        if 0 <= px < W and 0 <= py < H:
            bid = int(blob_grid[py, px])
            if bid != 0:
                return bid, gx, gy
    return 0, int(round(sample_x)), int(round(sample_y))


def ridge_ports(
    points: np.ndarray,
    idx_a: int,
    idx_b: int,
    v0: np.ndarray,
    v1: np.ndarray,
    blob_grid: np.ndarray,
    extent: tuple[int, int, int, int],
    edge_samples: int,
) -> list[tuple[int, int, int, int, int, int, int, int]]:
    """For one ridge, return port rows as tuples:
        (blob_a, blob_b, sample_start, sample_end, rep_a_x, rep_a_y, rep_b_x, rep_b_y)

    Contiguous samples with the same (blob_a, blob_b) pair collapse to one
    entry. Samples where either side has no walkable blob do not contribute.
    """
    ab = points[idx_a] - points[idx_b]
    norm = float(np.hypot(ab[0], ab[1]))
    if norm == 0.0:
        return []
    dir_a_x, dir_a_y = float(ab[0] / norm), float(ab[1] / norm)

    per_sample: list[tuple[int, int, int, int, int, int, int]] = []
    for i in range(edge_samples):
        t = i / max(1, edge_samples - 1)
        sx = float(v0[0] + t * (v1[0] - v0[0]))
        sy = float(v0[1] + t * (v1[1] - v0[1]))
        bid_a, ax, ay = lookup_blob_side(blob_grid, extent, sx, sy, dir_a_x, dir_a_y)
        bid_b, bx, by = lookup_blob_side(blob_grid, extent, sx, sy, -dir_a_x, -dir_a_y)
        per_sample.append((i, bid_a, bid_b, ax, ay, bx, by))

    # Group by (bid_a, bid_b); skip groups where either side is 0
    segments: list[tuple[int, int, int, int, int, int, int, int]] = []
    if not per_sample:
        return segments

    start = per_sample[0]
    current_key = (start[1], start[2])
    current_first = start
    current_last = start
    for entry in per_sample[1:]:
        key = (entry[1], entry[2])
        if key == current_key:
            current_last = entry
        else:
            if current_key[0] != 0 and current_key[1] != 0:
                mid = (current_first[0] + current_last[0]) // 2
                mid_entry = per_sample[mid]
                segments.append((
                    current_key[0], current_key[1],
                    current_first[0], current_last[0],
                    mid_entry[3], mid_entry[4],  # rep on side A
                    mid_entry[5], mid_entry[6],  # rep on side B
                ))
            current_key = key
            current_first = entry
            current_last = entry
    if current_key[0] != 0 and current_key[1] != 0:
        mid = (current_first[0] + current_last[0]) // 2
        mid_entry = per_sample[mid]
        segments.append((
            current_key[0], current_key[1],
            current_first[0], current_last[0],
            mid_entry[3], mid_entry[4],
            mid_entry[5], mid_entry[6],
        ))
    return segments


def ingest(db_path: Path, edge_samples: int = DEFAULT_EDGE_SAMPLES) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    bbox = conn.execute(
        "SELECT MIN(region_x), MAX(region_x), MIN(region_y), MAX(region_y) "
        "FROM map_squares WHERE plane = 0 AND type = 'blob'"
    ).fetchone()
    if bbox[0] is None:
        raise ValueError("No blob map squares in database. Run compute_blobs.py first.")
    x_min = bbox[0] * GAME_TILES_PER_REGION
    x_max = (bbox[1] + 1) * GAME_TILES_PER_REGION
    y_min = bbox[2] * GAME_TILES_PER_REGION
    y_max = (bbox[3] + 1) * GAME_TILES_PER_REGION

    print("Loading blob map squares...")
    blob_grid, extent = MapSquare.stitch_blobs(conn, x_min, x_max, y_min, y_max)
    print(f"Blob grid: {blob_grid.shape[1]}x{blob_grid.shape[0]} tiles")

    # Dependent edges reference ports.id; wipe them first so the delete below
    # doesn't trip the foreign-key check.
    conn.execute("DELETE FROM port_transits")
    conn.execute("DELETE FROM port_crossings")
    conn.execute("DELETE FROM ports")

    port_rows: list[tuple[int, int, int, int, int, int, int, int]] = []

    for world_name, y_op, y_threshold in [("overworld", "<", Y_WORLD_SPLIT), ("underworld", ">=", Y_WORLD_SPLIT)]:
        rows = conn.execute(
            f"SELECT id, x, y FROM locations "
            f"WHERE x IS NOT NULL AND y IS NOT NULL AND y {y_op} ?",
            (y_threshold,),
        ).fetchall()
        if len(rows) < 4:
            print(f"{world_name}: {len(rows)} locations, skipping")
            continue

        loc_ids = [r[0] for r in rows]
        points = np.array([(r[1], r[2]) for r in rows], dtype=np.float64)
        print(f"{world_name}: {len(rows)} cells, computing Voronoi...")
        vor = Voronoi(points)

        ridge_count = 0
        port_count = 0
        for ridge_idx, simplex in enumerate(vor.ridge_vertices):
            if -1 in simplex:
                continue
            idx_a, idx_b = int(vor.ridge_points[ridge_idx][0]), int(vor.ridge_points[ridge_idx][1])
            v0 = vor.vertices[simplex[0]]
            v1 = vor.vertices[simplex[1]]
            la = loc_ids[idx_a]
            lb = loc_ids[idx_b]
            ridge_a, ridge_b = (la, lb) if la < lb else (lb, la)

            segments = ridge_ports(points, idx_a, idx_b, v0, v1, blob_grid, extent, edge_samples)
            ridge_count += 1
            for blob_a, blob_b, s_start, s_end, ax, ay, bx, by in segments:
                port_rows.append((ridge_a, ridge_b, la, blob_a, s_start, s_end, ax, ay))
                port_rows.append((ridge_a, ridge_b, lb, blob_b, s_start, s_end, bx, by))
                port_count += 2

        print(f"{world_name}: {ridge_count} ridges -> {port_count} ports")

    print("Inserting ports...")
    conn.executemany(
        "INSERT INTO ports (ridge_location_a_id, ridge_location_b_id, side_location_id, "
        "blob_id, sample_start, sample_end, rep_x, rep_y) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        port_rows,
    )
    print(f"Inserted {len(port_rows)} ports")

    conn.commit()
    conn.close()
    print("Done")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute Voronoi-ridge ports grouped by blob")
    parser.add_argument("--db", type=Path, default=Path("data/ragger.db"))
    parser.add_argument("--edge-samples", type=int, default=DEFAULT_EDGE_SAMPLES)
    args = parser.parse_args()
    ingest(args.db, edge_samples=args.edge_samples)
