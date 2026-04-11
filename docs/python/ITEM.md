### Item (`src/ragger/item.py`)

```python
from ragger.item import Item

Item.all(conn) -> list[Item]
Item.by_name(conn, name) -> Item | None
Item.by_game_id(conn, game_id) -> Item | None
Item.search(conn, name) -> list[Item]
item.game_ids(conn) -> list[int]                       # from item_game_ids junction table
item.members -> bool | None
item.tradeable -> bool | None
item.weight -> float | None
item.examine -> str | None
```
