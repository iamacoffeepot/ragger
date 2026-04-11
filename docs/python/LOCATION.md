### Location (`src/ragger/location.py`)

```python
from ragger.location import Location, DistanceMetric

Location.all(conn, region?) -> list[Location]
Location.by_name(conn, name) -> Location | None
Location.search(conn, name) -> list[Location]      # partial name match
Location.nearest(conn, x, y, metric?) -> Location | None
Location.with_facilities(conn, [Facility, ...], region?) -> list[Location]
Location.for_shop(conn, shop_id) -> Location | None
location.adjacencies(conn) -> list[Adjacency]          # raw edges
location.neighbors(conn) -> dict[str, Location | None] # resolved by direction
location.within(conn, hops) -> list[tuple[Location, int]]  # BFS graph distance
location.nearby(conn, max_distance, metric?) -> list[tuple[Location, float]]  # tile distance
location.shops(conn) -> list[Shop]
location.has_facility(facility) -> bool
location.facility_list() -> list[Facility]
location.x -> int | None                               # map coordinates
location.y -> int | None
location.facilities -> int                             # bitmask
location.game_vars(conn) -> list[GameVariable]          # associated game variables
```

Distance metrics for `nearby()` and `nearest()`: `DistanceMetric.CHEBYSHEV` (default, matches OSRS diagonal movement), `DistanceMetric.MANHATTAN`, `DistanceMetric.EUCLIDEAN`. Distance computation is on the enum: `metric.compute(dx, dy)`.
