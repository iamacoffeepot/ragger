### Collision (`src/ragger/collision.py`)

Shared primitives for decoding the per-tile collision + water layers and
checking directional movement. Used by `compute_walkability.py` and
`compute_blobs.py`.

```python
from ragger.collision import (
    BLOCK_W, BLOCK_N, BLOCK_E, BLOCK_S, BLOCK_FULL, DATA_PRESENT,
    load_layers, build_flags_grid, can_move,
)

# Stitch every plane-0 map square into full-world layers
collision, water, color, x_min, x_max, y_min, y_max = load_layers(conn)

# Decode into an int32 flags grid indexed as flags[py, px] where
#   px = gx - x_min, py = y_max - 1 - gy
flags = build_flags_grid(collision, water)

# Can a unit at array coord (cy, cx) step to (cy + dy, cx + dx)?
can_move(flags, cy, cx, dy, dx, gh, gw) -> bool
```

### Flag bits

| Bit | Name | Meaning |
|-----|------|---------|
| `0x01` | `BLOCK_W` | Source tile blocks westward movement |
| `0x02` | `BLOCK_N` | Source tile blocks northward movement |
| `0x04` | `BLOCK_E` | Source tile blocks eastward movement |
| `0x08` | `BLOCK_S` | Source tile blocks southward movement |
| `0x10` | `BLOCK_FULL` | Tile is fully impassable (void, water, or wall-on-all-sides) |
| `0x20` | `DATA_PRESENT` | Set in the raw PNG; void tiles (no presence) become `BLOCK_FULL` |

### Coordinate conventions

- **Game coords**: `x` increases east, `y` increases north. Region at
  `(region_x, region_y)` covers `[64·region_x, 64·region_x + 64)` in x and
  similarly in y.
- **Array coords**: flags/blob grids are indexed as `[py, px]`. The y axis is
  flipped: `py = y_max - 1 - gy`. So array-dy `-1` corresponds to game-north
  (BLOCK_N on source), array-dy `+1` to game-south (BLOCK_S).

### `can_move` rules

- Destination must not be `BLOCK_FULL`.
- Cardinal: source must not have the outgoing block flag (N/S/E/W).
- Diagonal: source must clear *both* cardinal components, and the two
  intermediate cardinal tiles must be walkable and not block the diagonal's
  counterpart (e.g. a northeast step requires the east-intermediate tile to
  be walkable and not block north, and the north-intermediate tile to be
  walkable and not block east).

Water tiles are marked `BLOCK_FULL` by `build_flags_grid` via the stitched
water layer, so the walkability and blob pipelines treat water identically to
void.
