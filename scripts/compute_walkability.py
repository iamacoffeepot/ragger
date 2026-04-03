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


COLLISION_BLOCKED = (255, 0, 0)  # 0xFF0000 — red pixel in collision tiles
COLLISION_WALKABLE = (255, 255, 255)  # 0xFFFFFF — white pixel in collision tiles
WATER_BLUE = (0, 102, 204)  # 0x0066CC — blue pixel in water tiles


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


def make_blocked_checker(collision: np.ndarray, water: np.ndarray, x_min: int, x_max: int, y_min: int, y_max: int):
    """Return a function that checks if a game coordinate is blocked.

    Uses collision map (red = blocked) and water map (blue = water) directly.
    No heuristics — exact color matching against known constants.
    """
    height, width = collision.shape[:2]

    def is_blocked(gx: float, gy: float) -> bool:
        px = int(gx - x_min)
        py = int(y_max - 1 - gy)
        if px < 0 or py < 0 or px >= width or py >= height:
            return True
        cr, cg, cb = int(collision[py, px, 0]), int(collision[py, px, 1]), int(collision[py, px, 2])
        # Exact red = blocked
        if (cr, cg, cb) == COLLISION_BLOCKED:
            return True
        # Not exact white = no data / void
        if (cr, cg, cb) != COLLISION_WALKABLE:
            return True
        # Exact blue in water map = water
        wr, wg, wb = int(water[py, px, 0]), int(water[py, px, 1]), int(water[py, px, 2])
        if (wr, wg, wb) == WATER_BLUE:
            return True
        return False

    return is_blocked


def _flood_count(
    seeds: set[tuple[int, int]],
    blocked: np.ndarray,
    cell_mask: np.ndarray,
    gh: int, gw: int,
) -> int:
    """BFS from seeds, constrained to cell_mask, return number of pixels reached."""
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
        for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            ny, nx = cy + dy, cx + dx
            if 0 <= ny < gh and 0 <= nx < gw and not visited[ny, nx] and not blocked[ny, nx] and cell_mask[ny, nx]:
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
    is_blocked,
    resolution: int,
    edge_samples: int,
    area_threshold: float,
) -> bool:
    """Check if two Voronoi neighbors are walkable via edge flood fill.

    Samples points along the shared Voronoi edge, flood fills from walkable
    edge samples into each cell, and checks if the flood reaches a significant
    proportion of each cell's walkable area.
    """
    a = points[idx_a]
    b = points[idx_b]

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

    # Blocked grid (only check pixels in our two cells)
    blocked_grid = np.ones((gh, gw), dtype=bool)
    for gy in range(gh):
        for gx in range(gw):
            if mask_a[gy, gx] or mask_b[gy, gx]:
                game_x = bx_min + gx * resolution
                game_y = by_min + gy * resolution
                if not is_blocked(game_x, game_y):
                    blocked_grid[gy, gx] = False

    # Total walkable pixels in each cell
    walkable_a = int(np.sum(mask_a & ~blocked_grid))
    walkable_b = int(np.sum(mask_b & ~blocked_grid))
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
                if 0 <= ny < gh and 0 <= nx < gw and not blocked_grid[ny, nx]:
                    if mask_a[ny, nx]:
                        seeds_a.add((ny, nx))
                    elif mask_b[ny, nx]:
                        seeds_b.add((ny, nx))

    if not seeds_a or not seeds_b:
        return False

    # Flood fill from edge into each cell, measure reachable area
    reached_a = _flood_count(seeds_a, blocked_grid, mask_a, gh, gw)
    reached_b = _flood_count(seeds_b, blocked_grid, mask_b, gh, gw)

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
    is_blocked = make_blocked_checker(collision, water, x_min, x_max, y_min, y_max)
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
                v0, v1, tree, is_blocked,
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
