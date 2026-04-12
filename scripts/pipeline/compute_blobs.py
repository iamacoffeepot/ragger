"""Compute walkable connectivity blobs within each Voronoi cell.

For each Voronoi cell (location), flood fills walkable tiles using the full
collision model (directional walls, water, void, diagonal corner checks) and
assigns each maximal connected region a global blob ID.

The per-tile blob grid is written back as 16-bit PNG map squares of
`MapSquareType.BLOB` — one row per 64x64 region, pixel value = global blob ID
(0 = blocked / no blob). A companion `blobs` table maps each global ID to its
owning location and tile count so downstream consumers can reason about blob
membership without rasterizing.
"""

import argparse
import io
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import KDTree

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

plt.switch_backend("Agg")

Y_WORLD_SPLIT = 5000  # overworld < 5000 <= underworld (matches compute_walkability)
TILE_CHUNK = 1 << 20  # KDTree query chunk size for ownership pass


def compute_ownership(
    flags_grid: np.ndarray,
    x_min: int,
    y_max: int,
    points: np.ndarray,
    world_mask: np.ndarray,
) -> np.ndarray:
    """KDTree-query every tile in `world_mask` to its nearest Voronoi point.

    Returns an int32 array of the same shape as flags_grid; tiles outside
    `world_mask` are -1.
    """
    height, width = flags_grid.shape
    owners = np.full((height, width), -1, dtype=np.int32)
    tree = KDTree(points)

    py_idx, px_idx = np.nonzero(world_mask)
    n = py_idx.size
    if n == 0:
        return owners

    result = np.empty(n, dtype=np.int32)
    for start in range(0, n, TILE_CHUNK):
        end = min(start + TILE_CHUNK, n)
        py_chunk = py_idx[start:end]
        px_chunk = px_idx[start:end]
        gx = px_chunk.astype(np.float64) + x_min
        gy = (y_max - 1 - py_chunk).astype(np.float64)
        coords = np.column_stack((gx, gy))
        _, idx = tree.query(coords)
        result[start:end] = idx

    owners[py_idx, px_idx] = result
    return owners


def _direction_edges(
    flags: np.ndarray,
    walkable: np.ndarray,
    dy: int,
    dx: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (src_flat_idx, dst_flat_idx) for all tiles where `can_move` holds
    in direction (dy, dx), vectorized over the whole subgrid.

    `walkable` = cell-membership mask ∧ not-BLOCK_FULL.
    """
    H, W = flags.shape

    sy_lo, sy_hi = max(0, -dy), H - max(0, dy)
    sx_lo, sx_hi = max(0, -dx), W - max(0, dx)

    src = flags[sy_lo:sy_hi, sx_lo:sx_hi]
    dst = flags[sy_lo + dy:sy_hi + dy, sx_lo + dx:sx_hi + dx]
    src_walk = walkable[sy_lo:sy_hi, sx_lo:sx_hi]
    dst_walk = walkable[sy_lo + dy:sy_hi + dy, sx_lo + dx:sx_hi + dx]

    ok = src_walk & dst_walk

    if dx == 0 or dy == 0:
        # Cardinal: src must not have the outgoing block flag
        if dy == -1:
            ok &= (src & BLOCK_N) == 0
        elif dy == 1:
            ok &= (src & BLOCK_S) == 0
        elif dx == 1:
            ok &= (src & BLOCK_E) == 0
        elif dx == -1:
            ok &= (src & BLOCK_W) == 0
    else:
        # Diagonal: src must clear both cardinals, both intermediate tiles
        # must be walkable and not block the diagonal's counterpart flag
        h_flag = BLOCK_E if dx == 1 else BLOCK_W
        v_flag = BLOCK_N if dy == -1 else BLOCK_S
        ok &= (src & h_flag) == 0
        ok &= (src & v_flag) == 0

        # Horizontal intermediate tile at (sy, sx+dx): walkable, not block v_flag
        h_tile = flags[sy_lo:sy_hi, sx_lo + dx:sx_hi + dx]
        h_walk = walkable[sy_lo:sy_hi, sx_lo + dx:sx_hi + dx]
        ok &= h_walk
        ok &= (h_tile & v_flag) == 0

        # Vertical intermediate tile at (sy+dy, sx): walkable, not block h_flag
        v_tile = flags[sy_lo + dy:sy_hi + dy, sx_lo:sx_hi]
        v_walk = walkable[sy_lo + dy:sy_hi + dy, sx_lo:sx_hi]
        ok &= v_walk
        ok &= (v_tile & h_flag) == 0

    ly, lx = np.nonzero(ok)
    sy = ly + sy_lo
    sx = lx + sx_lo
    src_flat = sy.astype(np.int64) * W + sx
    dst_flat = (sy + dy).astype(np.int64) * W + (sx + dx)
    return src_flat, dst_flat


def cell_blobs(
    flags_local: np.ndarray,
    cell_mask: np.ndarray,
) -> tuple[np.ndarray, int]:
    """Label connected components within `cell_mask` under the directional
    movement predicate. Returns (labels, n_blobs) where labels has the same
    shape as flags_local with values in {0, 1, ..., n_blobs}. 0 = outside the
    cell or fully blocked.
    """
    H, W = flags_local.shape
    walkable = cell_mask & ((flags_local & BLOCK_FULL) == 0)
    walkable_count = int(walkable.sum())
    if walkable_count == 0:
        return np.zeros((H, W), dtype=np.int32), 0

    srcs: list[np.ndarray] = []
    dsts: list[np.ndarray] = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            s, d = _direction_edges(flags_local, walkable, dy, dx)
            if s.size:
                srcs.append(s)
                dsts.append(d)

    walkable_flat = walkable.ravel()
    walk_idx_flat = np.flatnonzero(walkable_flat)
    inv = np.full(H * W, -1, dtype=np.int64)
    inv[walk_idx_flat] = np.arange(walk_idx_flat.size)

    if srcs:
        src_flat = np.concatenate(srcs)
        dst_flat = np.concatenate(dsts)
        src_c = inv[src_flat]
        dst_c = inv[dst_flat]
        data = np.ones(src_c.size, dtype=np.uint8)
        graph = coo_matrix(
            (data, (src_c, dst_c)),
            shape=(walkable_count, walkable_count),
        ).tocsr()
        n_comp, comp_labels = connected_components(graph, directed=False)
    else:
        n_comp = walkable_count
        comp_labels = np.arange(walkable_count)

    labels_flat = np.zeros(H * W, dtype=np.int32)
    labels_flat[walk_idx_flat] = comp_labels + 1  # reserve 0
    return labels_flat.reshape(H, W), int(n_comp)


def encode_region_png(tile: np.ndarray) -> bytes:
    """Encode a 64x64 uint16 tile as a 16-bit grayscale PNG."""
    if tile.dtype != np.uint16:
        tile = tile.astype(np.uint16)
    img = Image.frombytes("I;16", (tile.shape[1], tile.shape[0]), tile.tobytes())
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _build_blob_adjacency(blob_grid: np.ndarray) -> dict[int, set[int]]:
    """Return adjacency sets keyed by blob id using 4-connectivity.

    Two distinct blobs are adjacent iff they share a cardinal-neighbor tile
    pair. Diagonal-only touches are ignored (they don't share a boundary
    edge, so sharing a color is visually unambiguous).
    """
    packed_edges: list[np.ndarray] = []
    for a_sl, b_sl in (
        ((slice(1, None), slice(None)), (slice(None, -1), slice(None))),  # N/S pair
        ((slice(None), slice(1, None)), (slice(None), slice(None, -1))),  # E/W pair
    ):
        a = blob_grid[a_sl].astype(np.int64)
        b = blob_grid[b_sl].astype(np.int64)
        diff = (a != b) & (a != 0) & (b != 0)
        if not diff.any():
            continue
        lo = np.minimum(a[diff], b[diff])
        hi = np.maximum(a[diff], b[diff])
        packed_edges.append((lo << 32) | hi)

    adj: dict[int, set[int]] = {}
    if not packed_edges:
        return adj

    unique = np.unique(np.concatenate(packed_edges))
    lo_arr = (unique >> 32).astype(np.int64)
    hi_arr = (unique & 0xFFFFFFFF).astype(np.int64)
    for lo, hi in zip(lo_arr.tolist(), hi_arr.tolist()):
        adj.setdefault(lo, set()).add(hi)
        adj.setdefault(hi, set()).add(lo)
    return adj


def _greedy_color(adj: dict[int, set[int]], all_ids: np.ndarray) -> tuple[np.ndarray, int]:
    """Welsh-Powell greedy coloring.

    Returns (color_lut, n_colors) where color_lut[blob_id] is the color index.
    Color 0 is reserved for "no blob" (blocked tiles).
    """
    max_id = int(all_ids.max()) if all_ids.size else 0
    color_lut = np.zeros(max_id + 1, dtype=np.uint8)

    # Sort blobs by degree descending; isolated blobs get color 1
    def degree(b: int) -> int:
        return len(adj.get(b, ()))
    order = sorted(all_ids.tolist(), key=lambda b: -degree(b))

    n_colors = 0
    for blob in order:
        used = {int(color_lut[n]) for n in adj.get(blob, ()) if color_lut[n] != 0}
        c = 1
        while c in used:
            c += 1
        color_lut[blob] = c
        if c > n_colors:
            n_colors = c
    return color_lut, n_colors


def render_debug_image(
    conn,
    blob_grid: np.ndarray,
    x_min: int,
    x_max: int,
    y_min: int,
    y_max: int,
    output_path: Path,
) -> None:
    """Render the blob grid as a 4-colored overlay on the color basemap."""
    print("Building blob adjacency graph...")
    adj = _build_blob_adjacency(blob_grid)
    all_ids = np.unique(blob_grid)
    all_ids = all_ids[all_ids != 0]
    print(f"  {len(adj)} adjacency entries, {len(all_ids)} blobs")

    print("Greedy-coloring blobs...")
    color_lut, n_colors = _greedy_color(adj, all_ids)
    print(f"  used {n_colors} colors")

    # Palette: first 4 are the four-color set, overflow uses extras so nothing
    # clashes if greedy overshoots 4 (Welsh-Powell isn't guaranteed optimal).
    palette = np.array([
        [0, 0, 0, 0],         # color 0 — transparent (no blob)
        [228, 26, 28, 200],   # red
        [55, 126, 184, 200],  # blue
        [77, 175, 74, 200],   # green
        [255, 210, 40, 200],  # yellow
        [152, 78, 163, 200],  # purple (fallback)
        [255, 127, 0, 200],   # orange (fallback)
        [166, 86, 40, 200],   # brown (fallback)
    ], dtype=np.uint8)
    if n_colors >= len(palette):
        raise RuntimeError(f"greedy coloring used {n_colors} colors, palette only has {len(palette) - 1}")

    color_grid = color_lut[blob_grid]
    rgba = palette[color_grid]

    print("Loading color basemap...")
    basemap, _ = MapSquare.stitch(conn, x_min, x_max, y_min, y_max, type=MapSquareType.COLOR, region_padding=0)

    fig, ax = plt.subplots(1, 1, figsize=(32, 32 * blob_grid.shape[0] / blob_grid.shape[1]))
    ax.imshow(basemap, extent=[x_min, x_max, y_min, y_max], aspect="equal", zorder=0)
    ax.imshow(rgba, extent=[x_min, x_max, y_min, y_max], aspect="equal", zorder=5, interpolation="nearest")
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_title(f"Blobs ({len(all_ids)} total, greedy {n_colors}-colored)", fontsize=14)
    ax.axis("off")
    plt.tight_layout()
    plt.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Debug image saved to {output_path}")


def ingest(db_path: Path, debug: bool = False) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    print("Loading collision / water layers...")
    bbox = conn.execute(
        "SELECT MIN(region_x), MAX(region_x), MIN(region_y), MAX(region_y) "
        "FROM map_squares WHERE plane = 0 AND type = 'collision'"
    ).fetchone()
    if bbox[0] is None:
        raise ValueError("No collision map squares in database. Run import_map_squares.py first.")
    x_min = bbox[0] * GAME_TILES_PER_REGION
    x_max = (bbox[1] + 1) * GAME_TILES_PER_REGION
    y_min = bbox[2] * GAME_TILES_PER_REGION
    y_max = (bbox[3] + 1) * GAME_TILES_PER_REGION

    collision, _ = MapSquare.stitch(conn, x_min, x_max, y_min, y_max, type=MapSquareType.COLLISION, region_padding=0)
    water, _ = MapSquare.stitch(conn, x_min, x_max, y_min, y_max, type=MapSquareType.WATER, region_padding=0)
    flags_grid = build_flags_grid(collision, water)
    del collision, water
    H, W = flags_grid.shape
    print(f"Full grid: {W}x{H} tiles ({x_min}-{x_max} x {y_min}-{y_max})")

    blob_grid = np.zeros((H, W), dtype=np.uint16)

    # Cascade clear all downstream tables that reference blobs.id — ports,
    # port_transits, port_crossings, blob_adjacencies, and map_link blob
    # columns — so the FK-protected DELETE FROM blobs below succeeds.
    conn.execute("DELETE FROM port_transits")
    conn.execute("DELETE FROM port_crossings")
    conn.execute("DELETE FROM blob_adjacencies")
    conn.execute("DELETE FROM ports")
    conn.execute("UPDATE map_links SET src_blob_id = NULL, dst_blob_id = NULL")
    conn.execute("DELETE FROM blobs")
    conn.execute(
        "DELETE FROM map_squares WHERE type = ?",
        (MapSquareType.BLOB.value,),
    )

    next_blob_id = 1  # 0 reserved for blocked / no blob
    blob_rows: list[tuple[int, int, int]] = []

    for world_name, y_op, y_threshold in [("overworld", "<", Y_WORLD_SPLIT), ("underworld", ">=", Y_WORLD_SPLIT)]:
        rows = conn.execute(
            f"SELECT id, name, x, y FROM locations "
            f"WHERE x IS NOT NULL AND y IS NOT NULL AND y {y_op} ?",
            (y_threshold,),
        ).fetchall()
        if len(rows) < 1:
            print(f"{world_name}: no locations, skipping")
            continue

        loc_ids = [r[0] for r in rows]
        points = np.array([(r[2], r[3]) for r in rows], dtype=np.float64)
        print(f"{world_name}: {len(rows)} Voronoi cells")

        py_all = np.arange(H, dtype=np.int32).reshape(-1, 1)
        gy_all = y_max - 1 - py_all
        if y_op == "<":
            row_mask_1d = (gy_all < y_threshold).ravel()
        else:
            row_mask_1d = (gy_all >= y_threshold).ravel()
        world_mask = np.broadcast_to(row_mask_1d[:, None], (H, W)).copy()

        print(f"{world_name}: computing Voronoi ownership...")
        owners = compute_ownership(flags_grid, x_min, y_max, points, world_mask)

        for cell_idx in range(len(rows)):
            cell_mask_full = owners == cell_idx
            if not cell_mask_full.any():
                continue
            ys, xs = np.nonzero(cell_mask_full)
            bby_min, bby_max = int(ys.min()), int(ys.max()) + 1
            bbx_min, bbx_max = int(xs.min()), int(xs.max()) + 1

            flags_local = flags_grid[bby_min:bby_max, bbx_min:bbx_max]
            cell_mask = cell_mask_full[bby_min:bby_max, bbx_min:bbx_max]

            labels, n_blobs = cell_blobs(flags_local, cell_mask)
            if n_blobs == 0:
                continue

            global_ids = np.arange(next_blob_id, next_blob_id + n_blobs, dtype=np.uint16)

            write_mask = labels > 0
            blob_grid[bby_min:bby_max, bbx_min:bbx_max][write_mask] = global_ids[labels[write_mask] - 1]

            counts = np.bincount(labels[write_mask], minlength=n_blobs + 1)[1:]
            for offset, cnt in enumerate(counts):
                blob_rows.append((next_blob_id + offset, loc_ids[cell_idx], int(cnt)))
            next_blob_id += n_blobs

            if (cell_idx + 1) % 50 == 0:
                print(f"  {world_name}: processed {cell_idx + 1}/{len(rows)} cells (global blob ids → {next_blob_id - 1})")

    conn.executemany(
        "INSERT INTO blobs (id, location_id, tile_count) VALUES (?, ?, ?)",
        blob_rows,
    )
    print(f"Inserted {len(blob_rows)} blobs")

    # Split blob_grid into 64x64 region tiles and write to map_squares
    print("Writing blob map squares...")
    row = conn.execute(
        "SELECT MIN(region_x), MAX(region_x), MIN(region_y), MAX(region_y) "
        "FROM map_squares WHERE plane = 0 AND type = 'collision'"
    ).fetchone()
    rx_min, rx_max, ry_min, ry_max = row

    square_inserts: list[tuple[int, int, int, str, bytes]] = []
    for ry in range(ry_min, ry_max + 1):
        for rx in range(rx_min, rx_max + 1):
            gx0 = rx * GAME_TILES_PER_REGION
            gy0 = ry * GAME_TILES_PER_REGION
            gx1 = gx0 + GAME_TILES_PER_REGION
            gy1 = gy0 + GAME_TILES_PER_REGION

            px0 = gx0 - x_min
            px1 = gx1 - x_min
            py0 = y_max - gy1  # top row of region in array coords
            py1 = y_max - gy0

            if px0 < 0 or py0 < 0 or px1 > W or py1 > H:
                continue

            tile = blob_grid[py0:py1, px0:px1]
            if not tile.any():
                continue  # skip regions with no walkable blobs (all water/void)

            png = encode_region_png(tile)
            square_inserts.append((0, rx, ry, MapSquareType.BLOB.value, png))

    conn.executemany(
        "INSERT INTO map_squares (plane, region_x, region_y, type, image) "
        "VALUES (?, ?, ?, ?, ?)",
        square_inserts,
    )
    print(f"Wrote {len(square_inserts)} blob map squares")

    conn.commit()

    if debug:
        render_debug_image(
            conn, blob_grid, x_min, x_max, y_min, y_max,
            Path("data/blobs_debug.png"),
        )

    conn.close()
    print("Done")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute per-cell walkable blobs")
    parser.add_argument("--db", type=Path, default=Path("data/ragger.db"))
    parser.add_argument("--debug", action="store_true", help="Render a 4-colored overlay of all blobs to data/blobs_debug.png")
    args = parser.parse_args()
    ingest(args.db, debug=args.debug)
