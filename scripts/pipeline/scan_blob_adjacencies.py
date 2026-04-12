"""Raster-scan the blob grid for walkably-adjacent cross-blob tile pairs.

Voronoi-ridge ports (see `compute_ports.py`) capture blob connectivity only
where a Voronoi ridge physically passes between two cells. When the Voronoi
diagram puts cell centroids close together (dense cities, dungeons), the
ridge between two cells can miss narrow passages like gates or corridors
entirely — the walkable sliver connecting two cells belongs to a third cell,
and no port ever spans it.

This pass ignores Voronoi geometry and works directly on the tile raster:
for every walkable tile pair (cy, cx) ↔ (cy+dy, cx+dx) where `can_move`
allows movement and the two tiles sit in different non-zero blobs, we record
one representative pair per unique `(blob_a_id, blob_b_id)` combination in
`blob_adjacencies`. The pathfinder unions these edges with port_transits and
port_crossings so A* can cross blob boundaries at tile-level connections the
ridge sampling missed.

Requires: `compute_blobs.py` to have been run first.
"""

import argparse
from pathlib import Path

import numpy as np

from ragger.collision import (
    BLOCK_E,
    BLOCK_FULL,
    BLOCK_N,
    BLOCK_S,
    BLOCK_W,
    build_flags_grid,
)
from ragger.db import create_tables, get_connection
from ragger.enums import MapSquareType
from ragger.map import GAME_TILES_PER_REGION, MapSquare


def _direction_mask(
    flags: np.ndarray,
    walkable: np.ndarray,
    dy: int,
    dx: int,
) -> np.ndarray:
    """Boolean array: can_move is valid from (py, px) in direction (dy, dx)."""
    H, W = flags.shape

    sy_lo, sy_hi = max(0, -dy), H - max(0, dy)
    sx_lo, sx_hi = max(0, -dx), W - max(0, dx)

    src = flags[sy_lo:sy_hi, sx_lo:sx_hi]
    src_walk = walkable[sy_lo:sy_hi, sx_lo:sx_hi]
    dst_walk = walkable[sy_lo + dy:sy_hi + dy, sx_lo + dx:sx_hi + dx]

    ok = src_walk & dst_walk

    if dx == 0 or dy == 0:
        if dy == -1:
            ok &= (src & BLOCK_N) == 0
        elif dy == 1:
            ok &= (src & BLOCK_S) == 0
        elif dx == 1:
            ok &= (src & BLOCK_E) == 0
        elif dx == -1:
            ok &= (src & BLOCK_W) == 0
    else:
        h_flag = BLOCK_E if dx == 1 else BLOCK_W
        v_flag = BLOCK_N if dy == -1 else BLOCK_S
        ok &= (src & h_flag) == 0
        ok &= (src & v_flag) == 0

        h_tile = flags[sy_lo:sy_hi, sx_lo + dx:sx_hi + dx]
        h_walk = walkable[sy_lo:sy_hi, sx_lo + dx:sx_hi + dx]
        ok &= h_walk
        ok &= (h_tile & v_flag) == 0

        v_tile = flags[sy_lo + dy:sy_hi + dy, sx_lo:sx_hi]
        v_walk = walkable[sy_lo + dy:sy_hi + dy, sx_lo:sx_hi]
        ok &= v_walk
        ok &= (v_tile & h_flag) == 0

    out = np.zeros((H, W), dtype=bool)
    out[sy_lo:sy_hi, sx_lo:sx_hi] = ok
    return out


def ingest(db_path: Path) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    bbox = conn.execute(
        "SELECT MIN(region_x), MAX(region_x), MIN(region_y), MAX(region_y) "
        "FROM map_squares WHERE plane = 0 AND type = 'collision'"
    ).fetchone()
    if bbox[0] is None:
        raise ValueError("No collision map squares. Run import_map_squares.py first.")
    x_min = bbox[0] * GAME_TILES_PER_REGION
    x_max = (bbox[1] + 1) * GAME_TILES_PER_REGION
    y_min = bbox[2] * GAME_TILES_PER_REGION
    y_max = (bbox[3] + 1) * GAME_TILES_PER_REGION

    print("Loading collision + water + blob layers...")
    collision, _ = MapSquare.stitch(conn, x_min, x_max, y_min, y_max, type=MapSquareType.COLLISION, region_padding=0)
    water, _ = MapSquare.stitch(conn, x_min, x_max, y_min, y_max, type=MapSquareType.WATER, region_padding=0)
    flags_grid = build_flags_grid(collision, water)
    del collision, water

    blob_grid, extent = MapSquare.stitch_blobs(conn, x_min, x_max, y_min, y_max)
    H, W = blob_grid.shape
    assert blob_grid.shape == flags_grid.shape, "blob and flags grids must align"
    gx_min, _gx_max, _gy_min, gy_max = extent

    walkable = blob_grid != 0

    # Collect one representative per spatially-distinct cluster of witness
    # tile-pairs for each unique (blob_a, blob_b) pair. Using one rep per
    # blob-pair forces A* through a single crossing coord even when the
    # boundary is long; a spatial grid of reps (every MIN_SEP tiles) gives
    # A* multiple crossing options so it can pick one close to the actual
    # path — fixing the "walk around to one corner then back" symptom.
    MIN_SEP = 15  # tiles; new rep emitted only if >MIN_SEP from existing reps

    # For each (a, b) pair store list of (ax, ay, bx, by) reps accepted so far
    pairs: dict[tuple[int, int], list[tuple[int, int, int, int]]] = {}

    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            mask = _direction_mask(flags_grid, walkable, dy, dx)
            if not mask.any():
                continue
            ys, xs = np.nonzero(mask)
            blob_src = blob_grid[ys, xs]
            blob_dst = blob_grid[ys + dy, xs + dx]
            cross = blob_src != blob_dst
            if not cross.any():
                continue
            ys = ys[cross]
            xs = xs[cross]
            bs = blob_src[cross].astype(np.int64)
            bd = blob_dst[cross].astype(np.int64)

            for i in range(ys.shape[0]):
                raw_a, raw_b = int(bs[i]), int(bd[i])
                a, b = (raw_a, raw_b) if raw_a < raw_b else (raw_b, raw_a)
                if raw_a == a:
                    ax = int(xs[i]) + gx_min
                    ay = int(gy_max - 1 - ys[i])
                    bx = int(xs[i] + dx) + gx_min
                    by = int(gy_max - 1 - (ys[i] + dy))
                else:
                    bx = int(xs[i]) + gx_min
                    by = int(gy_max - 1 - ys[i])
                    ax = int(xs[i] + dx) + gx_min
                    ay = int(gy_max - 1 - (ys[i] + dy))

                existing = pairs.setdefault((a, b), [])
                too_close = any(
                    max(abs(ax - ex), abs(ay - ey)) < MIN_SEP
                    for ex, ey, _, _ in existing
                )
                if not too_close:
                    existing.append((ax, ay, bx, by))

    n_pairs = len(pairs)
    n_reps = sum(len(v) for v in pairs.values())
    print(f"Found {n_pairs} unique blob-adjacency pairs ({n_reps} total reps, ~{n_reps / max(n_pairs, 1):.1f} per pair)")

    conn.execute("DELETE FROM blob_adjacencies")

    rows: list[tuple[int, int, int, int, int, int, int]] = []
    for (a, b), reps in pairs.items():
        for ax, ay, bx, by in reps:
            dist = max(abs(ax - bx), abs(ay - by))
            rows.append((a, b, ax, ay, bx, by, dist))
            rows.append((b, a, bx, by, ax, ay, dist))

    conn.executemany(
        "INSERT INTO blob_adjacencies (blob_a_id, blob_b_id, a_x, a_y, b_x, b_y, distance) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    print(f"Inserted {len(rows)} directed adjacency rows")

    conn.commit()
    conn.close()
    print("Done")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan blob raster for walkably-adjacent cross-blob tile pairs")
    parser.add_argument("--db", type=Path, default=Path("data/ragger.db"))
    args = parser.parse_args()
    ingest(args.db)
