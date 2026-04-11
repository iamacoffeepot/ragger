### Activity (`src/ragger/activity.py`)

```python
from ragger.activity import Activity

Activity.all(conn, region?, activity_type?) -> list[Activity]
Activity.by_name(conn, name) -> Activity | None
Activity.search(conn, name) -> list[Activity]          # partial name match
Activity.by_type(conn, activity_type) -> list[Activity]
Activity.for_skill(conn, skill) -> list[Activity]      # bitmask match
activity.skill_list() -> list[Skill]
activity.type -> ActivityType
activity.members -> bool
activity.location -> str | None
activity.location_id -> int | None                     # FK to locations table
activity.x -> int | None                               # map coordinates
activity.y -> int | None
activity.players -> str | None
activity.skills -> int                                 # bitmask
activity.region -> Region | None
activity.game_vars(conn) -> list[GameVariable]          # associated game variables
```
