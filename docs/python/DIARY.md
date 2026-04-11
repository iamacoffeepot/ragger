### DiaryTask (`src/ragger/diary.py`)

```python
from ragger.diary import DiaryTask

DiaryTask.all(conn, location?, tier?) -> list[DiaryTask]
task.requirement_groups(conn) -> list[RequirementGroup]
```

Diary XP rewards are on the enum: `DiaryLocation.xp_reward(tier)` and `DiaryLocation.min_level(tier)`.
