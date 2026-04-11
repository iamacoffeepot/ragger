"""Compute walkable connections between locations using Voronoi cells and edge flood fill.

For each pair of Voronoi neighbors, samples points along their shared edge,
flood fills from those edge samples into each cell, and checks if the flood
reaches a significant proportion of each cell's walkable area. This handles
cells split by rivers or narrow obstacles — only the portion reachable from
the shared edge counts.

Stores walkable pairs as map links with type "walkable".
"""

import argparse
from collections import deque
from pathlib import Path

import numpy as np
from scipy.spatial import KDTree, Voronoi

from ragger.db import create_tables, get_connection
from ragger.enums import MapLinkType, MapSquareType
from ragger.map import GAME_TILES_PER_REGION, MapSquare, PIXELS_PER_REGION


DEFAULT_RESOLUTION = 1  # game tiles per pixel in the flood fill grid
DEFAULT_AREA_THRESHOLD = 0.6  # proportion of cell walkable area reachable from edge
DEFAULT_EDGE_SAMPLES = 40  # sample points along the shared Voronoi edge


WATER_BLUE = (0, 102, 204)  # 0x0066CC — blue pixel in water tiles

# Collision flags encoded in pixel values (must match DumpCollision.java)
BLOCK_W = 0x1
BLOCK_N = 0x2
BLOCK_E = 0x4
BLOCK_S = 0x8
BLOCK_FULL = 0x10

# Direction table: (dx, dy, flag on source blocking this direction)
# Cardinals
_DIRS_CARDINAL = [
    (0, 1, BLOCK_N),   # north
    (0, -1, BLOCK_S),  # south
    (1, 0, BLOCK_E),   # east
    (-1, 0, BLOCK_W),  # west
]
# Diagonals: (dx, dy, horizontal cardinal flag, vertical cardinal flag)
_DIRS_DIAGONAL = [
    (1, 1, BLOCK_E, BLOCK_N),    # NE
    (-1, 1, BLOCK_W, BLOCK_N),   # NW
    (1, -1, BLOCK_E, BLOCK_S),   # SE
    (-1, -1, BLOCK_W, BLOCK_S),  # SW
]


def load_layers(conn) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int, int, int]:
    """Load collision, water, and color canvases from the database.

    Returns (collision, water, color, x_min, x_max, y_min, y_max).
    Collision and water are 1 px per tile. Color is 4 px per tile.
    """
    row = conn.execute(
        "SELECT MIN(region_x), MAX(region_x), MIN(region_y), MAX(region_y) "
        "FROM map_squares WHERE plane = 0 AND type = 'collision'"
    ).fetchone()
    if row[0] is None:
        raise ValueError("No collision map squares in database. Run import_map_squares.py first.")

    x_min = row[0] * GAME_TILES_PER_REGION
    x_max = (row[1] + 1) * GAME_TILES_PER_REGION
    y_min = row[2] * GAME_TILES_PER_REGION
    y_max = (row[3] + 1) * GAME_TILES_PER_REGION

    collision, _ = MapSquare.stitch(conn, x_min, x_max, y_min, y_max, type=MapSquareType.COLLISION, region_padding=0)
    water, _ = MapSquare.stitch(conn, x_min, x_max, y_min, y_max, type=MapSquareType.WATER, region_padding=0)
    color, _ = MapSquare.stitch(conn, x_min, x_max, y_min, y_max, type=MapSquareType.COLOR, region_padding=0)

    return collision, water, color, x_min, x_max, y_min, y_max


def build_flags_grid(collision: np.ndarray, water: np.ndarray, x_min: int, x_max: int, y_min: int, y_max: int) -> np.ndarray:
    """Build a 2D array of collision flags from the stitched collision and water images.

    Collision pixels encode raw directional flags in their RGB channels.
    Water pixels add BLOCK_FULL where blue.
    Returns an int32 array indexed as flags_grid[py, px] where
    px = gx - x_min, py = y_max - 1 - gy.
    """
    height, width = collision.shape[:2]

    # Decode flags from pixel RGB: flags = R | (G << 8) | (B << 16)
    flags_grid = (
        collision[:, :, 0].astype(np.int32)
        | (collision[:, :, 1].astype(np.int32) << 8)
        | (collision[:, :, 2].astype(np.int32) << 16)
    )

    # Mark water tiles as fully blocked
    water_mask = (
        (water[:, :, 0] == WATER_BLUE[0])
        & (water[:, :, 1] == WATER_BLUE[1])
        & (water[:, :, 2] == WATER_BLUE[2])
    )
    flags_grid[water_mask] |= BLOCK_FULL

    # Mark void tiles (where collision pixel is all zero = no data) as fully blocked
    void_mask = (collision[:, :, 0] == 0) & (collision[:, :, 1] == 0) & (collision[:, :, 2] == 0)
    flags_grid[void_mask] |= BLOCK_FULL

    return flags_grid


def make_blocked_checker(flags_grid: np.ndarray, x_min: int, x_max: int, y_min: int, y_max: int):
    """Return a function that checks if a game coordinate is fully blocked.

    Used for the simple blocked grid in flood_fill_check. For directional
    checks, use can_move() with the flags grid directly.
    """
    height, width = flags_grid.shape

    def is_blocked(gx: float, gy: float) -> bool:
        px = int(gx - x_min)
        py = int(y_max - 1 - gy)
        if px < 0 or py < 0 or px >= width or py >= height:
            return True
        return (flags_grid[py, px] & BLOCK_FULL) != 0

    return is_blocked


def _can_move(flags_grid: np.ndarray, cy: int, cx: int, dy: int, dx: int, gh: int, gw: int) -> bool:
    """Check if movement from (cy, cx) in direction (dy, dx) is allowed.

    Note: the flags grid is indexed as [py, px] where py increases upward in
    game coords but downward in array coords. dy in array coords is inverted
    from game coords: array dy=-1 means game north, dy=+1 means game south.

    Game direction mapping (array coords):
      dy=-1 (up in array = north in game) -> BLOCK_N
      dy=+1 (down in array = south in game) -> BLOCK_S
      dx=+1 (right = east) -> BLOCK_E
      dx=-1 (left = west) -> BLOCK_W
    """
    ny, nx = cy + dy, cx + dx
    if ny < 0 or ny >= gh or nx < 0 or nx >= gw:
        return False

    src = int(flags_grid[cy, cx])
    dst = int(flags_grid[ny, nx])

    # Destination fully blocked
    if dst & BLOCK_FULL:
        return False

    # Cardinal movement
    if dx == 0 or dy == 0:
        # Map array direction to game direction flag on source
        if dy == -1:
            return not (src & BLOCK_N)
        elif dy == 1:
            return not (src & BLOCK_S)
        elif dx == 1:
            return not (src & BLOCK_E)
        elif dx == -1:
            return not (src & BLOCK_W)

    # Diagonal movement — check both cardinal components on source
    h_flag = BLOCK_E if dx == 1 else BLOCK_W
    v_flag = BLOCK_N if dy == -1 else BLOCK_S

    # Source must not block the diagonal's cardinal components
    if src & h_flag or src & v_flag:
        return False

    # Intermediate cardinal tiles must be passable
    hx_y, hx_x = cy, cx + dx  # horizontal step
    vy_y, vy_x = cy + dy, cx  # vertical step

    if 0 <= hx_y < gh and 0 <= hx_x < gw:
        h_tile = int(flags_grid[hx_y, hx_x])
        if h_tile & BLOCK_FULL:
            return False
        if h_tile & v_flag:
            return False
    else:
        return False

    if 0 <= vy_y < gh and 0 <= vy_x < gw:
        v_tile = int(flags_grid[vy_y, vy_x])
        if v_tile & BLOCK_FULL:
            return False
        if v_tile & h_flag:
            return False
    else:
        return False

    return True


def _flood_count(
    seeds: set[tuple[int, int]],
    flags_local: np.ndarray,
    cell_mask: np.ndarray,
    gh: int, gw: int,
) -> int:
    """BFS from seeds using directional collision checks, constrained to cell_mask."""
    visited = np.zeros((gh, gw), dtype=bool)
    queue = deque()
    count = 0
    for sy, sx in seeds:
        if not visited[sy, sx]:
            visited[sy, sx] = True
            queue.append((sy, sx))
            count += 1
    while queue:
        cy, cx = queue.popleft()
        # 8-directional movement
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < gh and 0 <= nx < gw and not visited[ny, nx] and cell_mask[ny, nx]:
                    if _can_move(flags_local, cy, cx, dy, dx, gh, gw):
                        visited[ny, nx] = True
                        queue.append((ny, nx))
                        count += 1
    return count


def flood_fill_check(
    points: np.ndarray,
    idx_a: int,
    idx_b: int,
    v0: np.ndarray,
    v1: np.ndarray,
    tree: KDTree,
    flags_grid: np.ndarray,
    x_min: int,
    y_max: int,
    resolution: int,
    edge_samples: int,
    area_threshold: float,
) -> bool:
    """Check if two Voronoi neighbors are walkable via edge flood fill.

    Samples points along the shared Voronoi edge, flood fills from walkable
    edge samples into each cell using directional collision checks, and
    verifies that the flood reaches a significant proportion of each cell's
    walkable area.
    """
    a = points[idx_a]
    b = points[idx_b]
    full_h, full_w = flags_grid.shape

    # Bounding box covering both cells and the edge
    pad = max(abs(a[0] - b[0]), abs(a[1] - b[1])) * 0.5 + 50
    bx_min = int(min(a[0], b[0], v0[0], v1[0]) - pad)
    bx_max = int(max(a[0], b[0], v0[0], v1[0]) + pad)
    by_min = int(min(a[1], b[1], v0[1], v1[1]) - pad)
    by_max = int(max(a[1], b[1], v0[1], v1[1]) + pad)

    gw = (bx_max - bx_min) // resolution + 1
    gh = (by_max - by_min) // resolution + 1

    if gw <= 0 or gh <= 0 or gw > 2000 or gh > 2000:
        return False

    # Build ownership grid
    grid_coords = np.empty((gh * gw, 2))
    for gy in range(gh):
        for gx in range(gw):
            grid_coords[gy * gw + gx, 0] = bx_min + gx * resolution
            grid_coords[gy * gw + gx, 1] = by_min + gy * resolution
    _, owners = tree.query(grid_coords)
    owners = owners.reshape(gh, gw)

    mask_a = owners == idx_a
    mask_b = owners == idx_b

    # Build local flags grid from the global one
    flags_local = np.full((gh, gw), BLOCK_FULL, dtype=np.int32)
    for gy in range(gh):
        for gx in range(gw):
            if mask_a[gy, gx] or mask_b[gy, gx]:
                game_x = bx_min + gx * resolution
                game_y = by_min + gy * resolution
                fpx = game_x - x_min
                fpy = y_max - 1 - game_y
                if 0 <= fpx < full_w and 0 <= fpy < full_h:
                    flags_local[gy, gx] = flags_grid[fpy, fpx]
                # else: stays BLOCK_FULL (out of bounds)

    # Total walkable pixels in each cell (not fully blocked)
    not_blocked = (flags_local & BLOCK_FULL) == 0
    walkable_a = int(np.sum(mask_a & not_blocked))
    walkable_b = int(np.sum(mask_b & not_blocked))
    if walkable_a == 0 or walkable_b == 0:
        return False

    # Sample points along the shared Voronoi edge, collect seeds near the edge
    seeds_a: set[tuple[int, int]] = set()
    seeds_b: set[tuple[int, int]] = set()
    for i in range(edge_samples):
        t = i / max(1, edge_samples - 1)
        ex = v0[0] + t * (v1[0] - v0[0])
        ey = v0[1] + t * (v1[1] - v0[1])
        gx = int((ex - bx_min) / resolution)
        gy = int((ey - by_min) / resolution)
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                ny, nx = gy + dy, gx + dx
                if 0 <= ny < gh and 0 <= nx < gw and not (flags_local[ny, nx] & BLOCK_FULL):
                    if mask_a[ny, nx]:
                        seeds_a.add((ny, nx))
                    elif mask_b[ny, nx]:
                        seeds_b.add((ny, nx))

    if not seeds_a or not seeds_b:
        return False

    # Flood fill from edge into each cell, measure reachable area
    reached_a = _flood_count(seeds_a, flags_local, mask_a, gh, gw)
    reached_b = _flood_count(seeds_b, flags_local, mask_b, gh, gw)

    ratio_a = reached_a / walkable_a
    ratio_b = reached_b / walkable_b

    return ratio_a >= area_threshold and ratio_b >= area_threshold



def render_debug_image(
    canvas: np.ndarray,
    x_min: int, x_max: int, y_min: int, y_max: int,
    vor, points, rows, edge_results: list[tuple[int, bool]],
    output_path: Path,
) -> None:
    """Render a debug image showing walkable (green) and blocked (red) Voronoi edges."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    region_colors = {
        0: (0.5, 0.5, 0.5), 1: (0.27, 0.53, 1.0), 2: (1.0, 0.8, 0.27),
        3: (0.27, 0.73, 1.0), 4: (0.27, 1.0, 0.53), 5: (1.0, 0.53, 0.27),
        6: (0.67, 0.27, 1.0), 7: (1.0, 0.27, 0.27), 8: (1.0, 0.53, 1.0),
        9: (0.27, 1.0, 0.8), 10: (1.0, 0.27, 0.67), 11: (0.4, 0.4, 0.4),
    }

    fig, ax = plt.subplots(1, 1, figsize=(40, 28))
    ax.imshow(canvas, extent=[x_min, x_max, y_min, y_max], aspect="equal", zorder=0)

    for ridge_idx, is_walkable in edge_results:
        simplex = vor.ridge_vertices[ridge_idx]
        if -1 in simplex:
            continue
        v0 = vor.vertices[simplex[0]]
        v1 = vor.vertices[simplex[1]]
        color = "lime" if is_walkable else "red"
        ax.plot([v0[0], v1[0]], [v0[1], v1[1]], color=color, linewidth=0.6, alpha=0.8, zorder=5)

    for name, x, y, region in rows:
        color = region_colors.get(region, (0.5, 0.5, 0.5))
        ax.plot(x, y, "o", color=color, markersize=3, markeredgecolor="white", markeredgewidth=0.3, zorder=10)
        ax.text(x, y + 8, name, fontsize=2, color="white", ha="center", va="bottom", zorder=11, fontweight="bold")

    ax.plot([], [], "-", color="lime", linewidth=2, label="Walkable")
    ax.plot([], [], "-", color="red", linewidth=2, label="Blocked")
    ax.legend(loc="upper left", fontsize=10, framealpha=0.8)

    xs = [r[1] for r in rows]
    ys = [r[2] for r in rows]
    pad = 100
    ax.set_xlim(min(xs) - pad, max(xs) + pad)
    ax.set_ylim(min(ys) - pad, max(ys) + pad)
    ax.set_title("OSRS Voronoi Walkability — Overworld", fontsize=20)
    plt.tight_layout()
    plt.savefig(str(output_path), dpi=300)
    plt.close()
    print(f"Debug image saved to {output_path}")


def ingest(db_path: Path, resolution: int, area_threshold: float, edge_samples: int, debug: bool = False) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    print("Loading map layers from database...")
    collision, water, color, x_min, x_max, y_min, y_max = load_layers(conn)
    flags_grid = build_flags_grid(collision, water, x_min, x_max, y_min, y_max)
    print(f"Collision: {collision.shape[1]}x{collision.shape[0]} px, game coords {x_min}-{x_max} x {y_min}-{y_max}")

    for world_name, y_op, y_threshold in [("overworld", "<", 5000), ("underworld", ">=", 5000)]:
        rows = conn.execute(
            f"SELECT name, x, y, region FROM locations WHERE x IS NOT NULL AND y IS NOT NULL AND y {y_op} ?",
            (y_threshold,),
        ).fetchall()

        if len(rows) < 4:
            print(f"{world_name}: only {len(rows)} locations, skipping")
            continue

        points = np.array([(r[1], r[2]) for r in rows])
        names = [r[0] for r in rows]

        print(f"{world_name}: Computing Voronoi with {len(rows)} locations...")
        vor = Voronoi(points)
        tree = KDTree(points)

        walkable = 0
        blocked = 0
        edge_results: list[tuple[int, bool]] = []

        total_edges = sum(1 for s in vor.ridge_vertices if -1 not in s)
        print(f"{world_name}: Checking {total_edges} edges...")

        for ridge_idx, simplex in enumerate(vor.ridge_vertices):
            if -1 in simplex:
                continue

            v0 = vor.vertices[simplex[0]]
            v1 = vor.vertices[simplex[1]]
            pt_indices = vor.ridge_points[ridge_idx]
            loc_a = names[pt_indices[0]]
            loc_b = names[pt_indices[1]]

            is_walkable = flood_fill_check(
                points, pt_indices[0], pt_indices[1],
                v0, v1, tree, flags_grid, x_min, y_max,
                resolution, edge_samples, area_threshold,
            )

            edge_results.append((ridge_idx, is_walkable))

            if is_walkable:
                conn.execute(
                    """INSERT INTO map_links
                       (src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (loc_a, loc_b,
                     int(points[pt_indices[0]][0]), int(points[pt_indices[0]][1]),
                     int(points[pt_indices[1]][0]), int(points[pt_indices[1]][1]),
                     MapLinkType.WALKABLE.value,
                     f"Voronoi walkable: {loc_a} <-> {loc_b}"),
                )
                conn.execute(
                    """INSERT INTO map_links
                       (src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (loc_b, loc_a,
                     int(points[pt_indices[1]][0]), int(points[pt_indices[1]][1]),
                     int(points[pt_indices[0]][0]), int(points[pt_indices[0]][1]),
                     MapLinkType.WALKABLE.value,
                     f"Voronoi walkable: {loc_b} <-> {loc_a}"),
                )
                walkable += 1
            else:
                blocked += 1

        print(f"{world_name}: {walkable} walkable pairs, {blocked} blocked")

        if debug and world_name == "overworld":
            render_debug_image(
                color, x_min, x_max, y_min, y_max,
                vor, points, rows, edge_results,
                Path("data/walkability_debug.png"),
            )

    conn.commit()
    print("Done")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute walkability from map tiles")
    parser.add_argument("--db", type=Path, default=Path("data/ragger.db"))
    parser.add_argument("--resolution", type=int, default=DEFAULT_RESOLUTION)
    parser.add_argument("--area-threshold", type=float, default=DEFAULT_AREA_THRESHOLD)
    parser.add_argument("--edge-samples", type=int, default=DEFAULT_EDGE_SAMPLES)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    ingest(args.db, args.resolution, args.area_threshold, args.edge_samples, args.debug)
