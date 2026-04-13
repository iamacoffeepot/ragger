### MapLink (`src/ragger/map.py`)

```python
from ragger.map import MapLink

MapLink.all(conn, link_type?) -> list[MapLink]
MapLink.departing(conn, location, link_type?) -> list[MapLink]   # links FROM a location
MapLink.arriving(conn, location, link_type?) -> list[MapLink]    # links TO a location
MapLink.between(conn, location_a, location_b, link_type?) -> list[MapLink]
MapLink.reachable_from(conn, location) -> dict[str, list[MapLink]]
link.src_location -> str
link.dst_location -> str
link.src_x -> int
link.src_y -> int
link.dst_x -> int
link.dst_y -> int
link.link_type -> MapLinkType
link.description -> str | None
```

### MapSquare (`src/ragger/map.py`)

Map tile images with collision data from the OSRS game cache.

```python
from ragger.map import MapSquare

MapSquare.get(conn, plane, region_x, region_y, type=MapSquareType.COLOR) -> MapSquare | None
MapSquare.all(conn, plane=0, type=MapSquareType.COLOR) -> list[MapSquare]
MapSquare.at_game_coord(conn, x, y, plane=0, type=MapSquareType.COLOR) -> MapSquare | None
MapSquare.count(conn, plane=0, type?) -> int
MapSquare.stitch(conn, x_min, x_max, y_min, y_max, plane=0, type=MapSquareType.COLOR, region_padding=1, pixels_per_tile=None) -> (ndarray, extent)
square.game_x -> int                                   # region origin in game coords
square.game_y -> int
square.image -> bytes                                   # PNG image data
```

### Pathfinding (`src/ragger/map.py`)

```python
from ragger.map import find_path, render_path, PathStep, blob_at
from ragger.enums import MapLinkType

# Blob at a tile (0 = blocked / no blob)
blob_at(conn, x, y, plane=0) -> int

# A* from (src_x, src_y) to (dst_x, dst_y) through the port graph.
# Returns list of PathStep (walk segments + portal traversals), or None.
find_path(conn, src_x, src_y, dst_x, dst_y) -> list[PathStep] | None
find_path(conn, src_x, src_y, dst_x, dst_y, allowed_types={...}) -> list[PathStep] | None

# Filter by MapLinkType — disables portals of any excluded type. Walking
# always works (no type filter applies to port_transits / port_crossings).
find_path(conn, sx, sy, dx, dy, allowed_types=set())  # walking only
find_path(conn, sx, sy, dx, dy, allowed_types=set(MapLinkType) - {MapLinkType.TELEPORT})  # no teleports

# PathStep.link is None for walking segments, or the MapLink traversed for portals.
step.src_x, step.src_y, step.dst_x, step.dst_y
step.link               # MapLink | None
step.link_type          # MapLinkType (WALKABLE if link is None)
step.src_location       # "" for walk segments
step.dst_location       # "" for walk segments

# Render path as image (surface + underground stacked panels)
render_path(conn, path, "output.png", padding=200, dpi=200)

# Debug render: expand each walking run into its tile-by-tile route (BFS +
# string-pull to a natural octile path) and highlight every walked tile.
# Portal traversals draw as dashed magenta arrows. Slow — use for visual
# verification, not bulk rendering.
render_path_tiles(conn, path, "output.png", padding=80, dpi=200)
```

The pathfinder runs A* over a graph of port nodes (Voronoi-ridge endpoints per blob) plus virtual nodes at portal endpoints. Walking edges come from `port_transits` (exact BFS distances within a blob) and `port_crossings` (ridge crossings, Chebyshev between rep tiles). Portal edges come from `map_links` — each map_link becomes two virtual nodes at its `(src_x, src_y)` and `(dst_x, dst_y)` connected by the link's traversal cost, joined to nearby ports via the precomputed `src_blob_id` / `dst_blob_id` columns. ANYWHERE teleports seed the initial frontier directly with their activation cost. Requires: `compute_blobs` → `compute_ports` → `compute_port_transits` → `compute_port_crossings` → `compute_map_link_blobs`.
