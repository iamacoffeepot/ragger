### LeagueTask (`src/ragger/league.py`)

```python
from ragger.league import LeagueTask

LeagueTask.all(conn, difficulty?, region?) -> list[LeagueTask]
LeagueTask.by_name(conn, name) -> LeagueTask | None
LeagueTask.search(conn, name) -> list[LeagueTask]  # partial name match
LeagueTask.by_skill(conn, skill, difficulty?, region?) -> list[LeagueTask]
task.points -> int                                    # derived from difficulty
task.requirement_groups(conn) -> list[RequirementGroup]
task.skill_requirements(conn) -> list[GroupSkillRequirement]
task.quest_requirements(conn) -> list[GroupQuestRequirement]
task.item_requirements(conn) -> list[GroupItemRequirement]
task.diary_requirements(conn) -> list[GroupDiaryRequirement]
task.region_requirements(conn) -> list[GroupRegionRequirement]
```

### LeagueConfig (`src/ragger/league.py`)

```python
from ragger.league import LeagueConfig

config = LeagueConfig.from_yaml(Path("config/demonic-pacts.yaml"))
config.starting_region -> Region
config.starting_location -> str
config.always_accessible -> list[Region]
config.unlockable_regions -> list[Region]
config.max_region_unlocks -> int
config.starting_skills -> dict[Skill, int]
config.autocompleted_quests -> list[str]
config.completed_quests(conn, resolve_chains=True) -> list[Quest]
config.starting_quest_points(conn) -> int
config.available_regions(unlocked?) -> list[Region]
```

### Account (`src/ragger/league.py`)

Simulates league account progression — tracks XP, completed quests/tasks, and unlocked regions.

```python
from ragger.league import Account, LeagueConfig

config = LeagueConfig.from_yaml(Path("config/demonic-pacts.yaml"))
account = Account(config, conn)

# Progression
account.complete_quest(quest, xp_choices?) -> bool
account.complete_task(task) -> bool
account.unlock_region(region) -> bool
account.add_xp(skill, amount)
account.set_skill(skill, level)

# Queries
account.get_level(skill) -> int
account.get_xp(skill) -> int
account.has_quest(quest) -> bool
account.has_skill(skill, level) -> bool
account.has_region(region) -> bool
account.current_location -> str
account.quest_points -> int
account.league_points -> int
account.regions -> list[Region]

# Availability (with toggleable filters)
account.available_quests(check_skills?, check_regions?, check_quests?) -> list[Quest]
account.available_tasks(check_skills?, check_regions?, check_quests?) -> list[LeagueTask]
account.completed_quests() -> list[Quest]
account.completed_tasks() -> list[LeagueTask]
```
