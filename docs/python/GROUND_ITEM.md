### GroundItem (`src/ragger/ground_item.py`)

```python
from ragger.ground_item import GroundItem

GroundItem.all(conn, region?) -> list[GroundItem]
GroundItem.by_item_name(conn, name) -> list[GroundItem]
GroundItem.by_item_id(conn, item_id) -> list[GroundItem]
GroundItem.search(conn, name) -> list[GroundItem]       # LIKE %name%
GroundItem.at_location(conn, location_id) -> list[GroundItem]
GroundItem.near(conn, x, y, radius=50) -> list[GroundItem]
gi.item_name -> str
gi.item_id -> int | None                                # FK to items, linked by name normalization
gi.location -> str                                      # cleaned wiki location text
gi.location_id -> int | None                            # FK to locations, linked by nearest Chebyshev
gi.members -> bool
gi.x -> int
gi.y -> int
gi.plane -> int                                         # 0 = ground, 1+ = upper floors
gi.region -> Region | None
```

Also accessible from Location:

```python
location.ground_items(conn) -> list[GroundItem]
```
