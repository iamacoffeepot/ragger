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
from ragger.map import find_path, render_path
from ragger.enums import MapLinkType

# Find shortest path (considers ANYWHERE teleports as starting candidates)
find_path(conn, src, dst) -> list[MapLink] | None
find_path(conn, src, dst, allowed_types={...}) -> list[MapLink] | None

# Filter examples:
find_path(conn, src, dst, allowed_types={MapLinkType.WALKABLE, MapLinkType.ENTRANCE, MapLinkType.EXIT})  # walking only
find_path(conn, src, dst, allowed_types=set(MapLinkType) - {MapLinkType.TELEPORT})  # no teleports

# Render path as image (surface + underground stacked panels)
render_path(conn, path, "output.png", padding=200, dpi=200)
```

Pathfinding uses A* with Chebyshev heuristic. Zero cost for instant transitions (teleports, fairy rings, entrances). Walkable edges cost Chebyshev distance. Path rendering chains arrows end-to-end, snaps same-location coords, and splits into panels when jumps exceed 384 tiles (6 regions) with departure/arrival markers.
