"""Compute walkable connections between locations using Voronoi edges and map tile collision data.

Uses Euclidean Voronoi to determine which locations are neighbors, then samples
the map tiles along each edge to determine if the path is blocked (water, walls, void).

Stores walkable pairs as map links with type "walkable".

Requires: fetch_locations.py to have been run and data/map-squares.zip to exist.
"""

import argparse
import os
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.spatial import Voronoi

from clogger.db import create_tables, get_connection
from clogger.enums import MapLinkType


DEFAULT_THRESHOLD = 0.975
DEFAULT_SAMPLES = 200


def load_canvas(zip_path: Path) -> tuple[np.ndarray, int, int, int, int]:
    """Load ground plane tiles from zip and stitch into a canvas.

    Returns (canvas, x_min_game, x_max_game, y_min_game, y_max_game).
    """
    px_per_region = 256
    game_per_region = 64

    tiles: dict[tuple[int, int], bytes] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            m = re.match(r"0_(\d+)_(\d+)\.png", name)
            if m:
                tiles[(int(m.group(1)), int(m.group(2)))] = zf.read(name)

    rxs = [t[0] for t in tiles]
    rys = [t[1] for t in tiles]
    min_rx, max_rx = min(rxs), max(rxs)
    min_ry, max_ry = min(rys), max(rys)

    width = (max_rx - min_rx + 1) * px_per_region
    height = (max_ry - min_ry + 1) * px_per_region
    canvas = np.zeros((height, width, 3), dtype=np.uint8)

    for (rx, ry), data in tiles.items():
        try:
            tile = np.array(Image.open(__import__("io").BytesIO(data)).convert("RGB"))
            px = (rx - min_rx) * px_per_region
            py = (max_ry - ry) * px_per_region
            canvas[py:py + px_per_region, px:px + px_per_region] = tile
        except Exception:
            pass

    x_min = min_rx * game_per_region
    x_max = (max_rx + 1) * game_per_region
    y_min = min_ry * game_per_region
    y_max = (max_ry + 1) * game_per_region

    return canvas, x_min, x_max, y_min, y_max


def make_blocked_checker(canvas: np.ndarray, x_min: int, x_max: int, y_min: int, y_max: int):
    """Return a function that checks if a game coordinate is blocked."""
    height, width = canvas.shape[:2]

    def is_blocked(gx: float, gy: float) -> bool:
        px = int((gx - x_min) * 4)
        py = int((y_max - gy) * 4)
        if px < 0 or py < 0 or px >= width or py >= height:
            return True
        r, g, b = int(canvas[py, px, 0]), int(canvas[py, px, 1]), int(canvas[py, px, 2])
        # Red = collision flag from map renderer
        if r > 200 and g < 50 and b < 50:
            return True
        # Black/dark void (includes dark grey fill between regions)
        if r < 40 and g < 40 and b < 40:
            return True
        # Dark grey-blue map border (not ocean, not land)
        if r < 100 and g < 100 and b < 130 and abs(r - g) < 10 and b > r + 20:
            return True
        # Ocean blue
        if b > 120 and b > r + 20 and b > g:
            return True
        return False

    return is_blocked


def edge_blocked_ratio(v0, v1, is_blocked, num_samples: int) -> float:
    """Sample along an edge and return the ratio of blocked points."""
    blocked = 0
    for i in range(num_samples):
        t = i / (num_samples - 1)
        gx = v0[0] + t * (v1[0] - v0[0])
        gy = v0[1] + t * (v1[1] - v0[1])
        if is_blocked(gx, gy):
            blocked += 1
    return blocked / num_samples


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


def ingest(db_path: Path, threshold: float, samples: int, debug: bool = False) -> None:
    create_tables(db_path)
    conn = get_connection(db_path)

    zip_path = Path("data/map-squares.zip")
    if not zip_path.exists():
        print(f"Error: {zip_path} not found.")
        return

    print("Loading map tiles...")
    canvas, x_min, x_max, y_min, y_max = load_canvas(zip_path)
    is_blocked = make_blocked_checker(canvas, x_min, x_max, y_min, y_max)
    print(f"Canvas: {canvas.shape[1]}x{canvas.shape[0]} px, game coords {x_min}-{x_max} x {y_min}-{y_max}")

    # Process overworld and underworld separately
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

        walkable = 0
        blocked = 0
        edge_results: list[tuple[int, bool]] = []

        for ridge_idx, simplex in enumerate(vor.ridge_vertices):
            if -1 in simplex:
                continue

            v0 = vor.vertices[simplex[0]]
            v1 = vor.vertices[simplex[1]]

            pt_indices = vor.ridge_points[ridge_idx]
            loc_a = names[pt_indices[0]]
            loc_b = names[pt_indices[1]]

            ratio = edge_blocked_ratio(v0, v1, is_blocked, samples)
            is_walkable = ratio < threshold
            edge_results.append((ridge_idx, is_walkable))

            if is_walkable:
                conn.execute(
                    """INSERT INTO map_links
                       (from_location, to_location, from_x, from_y, to_x, to_y, type, description)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (loc_a, loc_b,
                     int(points[pt_indices[0]][0]), int(points[pt_indices[0]][1]),
                     int(points[pt_indices[1]][0]), int(points[pt_indices[1]][1]),
                     MapLinkType.WALKABLE.value,
                     f"Voronoi walkable: {loc_a} <-> {loc_b}"),
                )
                conn.execute(
                    """INSERT INTO map_links
                       (from_location, to_location, from_x, from_y, to_x, to_y, type, description)
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
                canvas, x_min, x_max, y_min, y_max,
                vor, points, rows, edge_results,
                Path("data/walkability_debug.png"),
            )

    conn.commit()
    print("Done")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute walkability from map tiles")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/clogger.db"),
        help="Path to the SQLite database",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Blocked ratio threshold (default {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=DEFAULT_SAMPLES,
        help=f"Number of samples per edge (default {DEFAULT_SAMPLES})",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Produce a debug image of overworld walkability edges",
    )
    args = parser.parse_args()
    ingest(args.db, args.threshold, args.samples, args.debug)
