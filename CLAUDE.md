# Clogger

OSRS Leagues knowledge base for route planning.

## Project Structure

- `src/clogger/` — Python package with data models and database module
- `scripts/` — Data ingestion scripts that pull from the OSRS wiki API
- `data/` — SQLite database (gitignored)
- `tests/` — pytest tests

## Scripts

All scripts require the package to be installed: `uv pip install -e .`

### fetch_all.py (recommended)

Runs all ingestion scripts in the correct order. Items must be populated first since other scripts reference the items table.

```sh
uv run python scripts/fetch_all.py [--db data/clogger.db] [--league Raging_Echoes_League/Tasks]
```

### Individual scripts

Run order matters: items -> quests -> quest regions -> diary tasks -> diary items -> shops -> locations -> link shops -> league tasks

- `fetch_items.py` — Pulls all item names from the OSRS wiki
- `fetch_quests.py` — Pulls quests with points, XP/item rewards, skill/quest/QP requirements
- `fetch_quest_regions.py` — Parses the `leagueRegion` infobox field from each quest's wiki page to map quests to regions
- `fetch_diary_tasks.py` — Pulls diary tasks with skill and quest requirements
- `fetch_diary_items.py` — Pulls diary task item requirements from the Achievement Diary overview page
- `fetch_shops.py` — Pulls shop data with items, stock, pricing, and shop type from Category:Shops
- `fetch_locations.py` — Pulls locations with adjacency graph, region, and map coordinates from Category:Locations
- `link_shop_locations.py` — Links shops to locations by matching location text
- `fetch_league_tasks.py` — Pulls league tasks with skill, quest, item, and diary requirements. Accepts `--page` for the wiki page to fetch from

All fetch scripts share utilities from `src/clogger/wiki.py` (API constants, category enumeration, wikitext fetching, template parsing, requirement linking).

## Database

Default path: `data/clogger.db`. All scripts accept `--db` to override.

Tables are created automatically when any script runs. Only `fetch_items.py` writes to the items table — all other scripts reference it.

## Python API

All API methods accept a `sqlite3.Connection` so connections can be reused.

### Quest (`src/clogger/quest.py`)

```python
from clogger.quest import Quest

Quest.all(conn) -> list[Quest]
Quest.by_name(conn, name) -> Quest | None
quest.xp_rewards(conn) -> list[ExperienceReward]
quest.item_rewards(conn) -> list[ItemReward]
quest.skill_requirements(conn) -> list[SkillRequirement]
quest.quest_requirements(conn) -> list[QuestRequirement]
quest.quest_point_requirement(conn) -> QuestPointRequirement | None
quest.requirement_chain(conn) -> list[Quest]       # flat list, bottom-up order
quest.requirement_tree(conn) -> str                 # indented tree string
```

### Item (`src/clogger/item.py`)

```python
from clogger.item import Item

Item.all(conn) -> list[Item]
Item.by_name(conn, name) -> Item | None
```

### DiaryTask (`src/clogger/diary.py`)

```python
from clogger.diary import DiaryTask

DiaryTask.all(conn, location?, tier?) -> list[DiaryTask]
```

Diary XP rewards are on the enum: `DiaryLocation.xp_reward(tier)` and `DiaryLocation.min_level(tier)`.

### LeagueTask (`src/clogger/league.py`)

```python
from clogger.league import LeagueTask

LeagueTask.all(conn, difficulty?, region?) -> list[LeagueTask]
LeagueTask.by_name(conn, name) -> LeagueTask | None
LeagueTask.by_skill(conn, skill, difficulty?, region?) -> list[LeagueTask]
task.points -> int                                    # derived from difficulty
task.skill_requirements(conn) -> list[SkillRequirement]
task.quest_requirements(conn) -> list[QuestRequirement]
task.item_requirements(conn) -> list[ItemRequirement]
task.diary_requirements(conn) -> list[DiaryRequirement]
task.region_requirements(conn) -> list[RegionRequirement]
```

### LeagueConfig (`src/clogger/league.py`)

```python
from clogger.league import LeagueConfig

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

### Account (`src/clogger/league.py`)

Simulates league account progression — tracks XP, completed quests/tasks, and unlocked regions.

```python
from clogger.league import Account, LeagueConfig

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

### Shop (`src/clogger/shop.py`)

```python
from clogger.shop import Shop, ShopItem

Shop.all(conn, region?, shop_type?) -> list[Shop]
Shop.by_name(conn, name) -> Shop | None
Shop.selling(conn, item_name, region?) -> list[Shop]
Shop.all_at(conn, location_id) -> list[Shop]
shop.items(conn) -> list[ShopItem]
shop.item_by_name(conn, item_name) -> ShopItem | None
shop.location_id -> int | None                        # FK to locations table
shop.shop_type -> ShopType
shop.sell_multiplier -> int                            # permille (1000 = 100%)
shop.buy_multiplier -> int
shop.delta -> int                                      # price change per stock unit
item.effective_sell_price(sell_multiplier, base_value) -> int
item.effective_buy_price(buy_multiplier, base_value) -> int
```

### Location (`src/clogger/location.py`)

```python
from clogger.location import Location, DistanceMetric

Location.all(conn, region?) -> list[Location]
Location.by_name(conn, name) -> Location | None
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
```

Distance metrics for `nearby()` and `nearest()`: `DistanceMetric.CHEBYSHEV` (default, matches OSRS diagonal movement), `DistanceMetric.MANHATTAN`, `DistanceMetric.EUCLIDEAN`. Distance computation is on the enum: `metric.compute(dx, dy)`.

### FacilityEntry (`src/clogger/facility.py`)

Raw facility coordinate data (banks, furnaces, anvils, altars, spinning wheels, looms).

```python
from clogger.facility import FacilityEntry
from clogger.enums import Facility

FacilityEntry.all(conn, facility_type?, region?) -> list[FacilityEntry]
FacilityEntry.nearest(conn, x, y, facility_type?, metric?) -> FacilityEntry | None
FacilityEntry.nearby(conn, x, y, max_distance, facility_type?, metric?) -> list[tuple[FacilityEntry, float]]
entry.type -> Facility
entry.x -> int
entry.y -> int
entry.name -> str | None
entry.region -> Region | None                          # derived from nearest location
```

## Enums (`src/clogger/enums.py`)

- `Skill(int, Enum)` — 23 OSRS skills, int-based with `label`, `mask` properties
- `Region(int, Enum)` — 12 regions (including GENERAL), int-based with `label`, `mask`, `from_label` properties
- `TaskDifficulty(int, Enum)` — Easy/Medium/Hard/Elite/Master with `label`, `points` properties
- `DiaryLocation(str, Enum)` — 12 diary regions with `xp_reward(tier)`, `min_level(tier)` methods
- `DiaryTier(str, Enum)` — Easy/Medium/Hard/Elite
- `ShopType(str, Enum)` — 36 shop types (General, Gem, Fishing, Magic, etc.) with `from_label` fuzzy matching
- `Facility(int, Enum)` — Bank, Furnace, Anvil, Range, Altar, Spinning wheel, Loom with `mask`, `label` properties
- `ALL_SKILLS_MASK`, `ALL_REGIONS_MASK` — bitmask constants for "all"

## Tests

```sh
uv run pytest
```
