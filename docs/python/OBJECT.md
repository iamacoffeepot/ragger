### ObjectLocation (`src/ragger/object.py`)

```python
from ragger.object import ObjectLocation

ObjectLocation.by_game_id(conn, game_id) -> list[ObjectLocation]
ObjectLocation.near(conn, x, y, radius=50, plane=0) -> list[ObjectLocation]
```
