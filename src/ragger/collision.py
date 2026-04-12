"""Shared collision/walkability primitives.

Loads stitched collision + water layers from the `map_squares` table, decodes
them into a single int32 flags grid, and provides the directional movement
predicate used by walkability and blob flood fills.

The flags grid is indexed as `flags[py, px]` where
`px = gx - x_min` and `py = y_max - 1 - gy` (y axis flipped: array-up is
game-south). Each tile packs directional wall flags, a fully-blocked bit,
and a presence bit (void tiles with no presence are treated as fully blocked).
"""

from __future__ import annotations

import sqlite3

import numpy as np

from ragger.enums import MapSquareType
from ragger.map import GAME_TILES_PER_REGION, MapSquare

# Collision flags encoded in pixel values (must match DumpCollision.java)
BLOCK_W = 0x1
BLOCK_N = 0x2
BLOCK_E = 0x4
BLOCK_S = 0x8
BLOCK_FULL = 0x10
DATA_PRESENT = 0x20

# Blue pixel value identifying water tiles
WATER_BLUE = (0, 102, 204)


def load_layers(conn: sqlite3.Connection) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int, int, int]:
    """Load stitched collision, water, and color layers covering every region.

    Returns (collision, water, color, x_min, x_max, y_min, y_max) where arrays
    are 1 px per tile (collision/water) or 4 px per tile (color).
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


def build_flags_grid(collision: np.ndarray, water: np.ndarray) -> np.ndarray:
    """Decode the stitched collision + water layers into an int32 flags grid.

    Void tiles (no DATA_PRESENT bit) and water tiles are marked BLOCK_FULL.
    Directional wall flags are preserved from the collision raster.
    """
    raw = collision[:, :, 2].astype(np.int32)

    void_mask = (raw & DATA_PRESENT) == 0
    flags = raw & ~DATA_PRESENT
    flags[void_mask] = BLOCK_FULL

    water_mask = (
        (water[:, :, 0] == WATER_BLUE[0])
        & (water[:, :, 1] == WATER_BLUE[1])
        & (water[:, :, 2] == WATER_BLUE[2])
    )
    flags[water_mask] |= BLOCK_FULL

    return flags


def can_move(flags: np.ndarray, cy: int, cx: int, dy: int, dx: int, gh: int, gw: int) -> bool:
    """Check if movement from (cy, cx) to (cy+dy, cx+dx) is allowed.

    Array dy is inverted from game y: dy=-1 is game-north (BLOCK_N on source),
    dy=+1 is game-south (BLOCK_S). Diagonals require both cardinal components
    to be clear on the source tile *and* the two intermediate cardinal tiles
    to be passable.
    """
    ny, nx = cy + dy, cx + dx
    if ny < 0 or ny >= gh or nx < 0 or nx >= gw:
        return False

    src = int(flags[cy, cx])
    dst = int(flags[ny, nx])

    if dst & BLOCK_FULL:
        return False

    if dx == 0 or dy == 0:
        if dy == -1:
            return not (src & BLOCK_N)
        if dy == 1:
            return not (src & BLOCK_S)
        if dx == 1:
            return not (src & BLOCK_E)
        if dx == -1:
            return not (src & BLOCK_W)

    h_flag = BLOCK_E if dx == 1 else BLOCK_W
    v_flag = BLOCK_N if dy == -1 else BLOCK_S

    if src & h_flag or src & v_flag:
        return False

    hx_y, hx_x = cy, cx + dx
    vy_y, vy_x = cy + dy, cx

    h_tile = int(flags[hx_y, hx_x])
    if h_tile & BLOCK_FULL or h_tile & v_flag:
        return False

    v_tile = int(flags[vy_y, vy_x])
    if v_tile & BLOCK_FULL or v_tile & h_flag:
        return False

    return True
