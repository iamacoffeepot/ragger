# Ragger

OSRS knowledge base powered by retrieval-augmented generation.

## Project Structure

- `src/ragger/` — Python package with data models and database module
- `scripts/` — Data ingestion scripts that pull from the OSRS wiki API
- `plugin/` — RuneLite plugin with AI chat panel and Wasm scripting engine
- `tools/cache-dump/` — Java tool for extracting map data from the OSRS game cache
- `data/` — SQLite database and cache dump output (gitignored)
- `tests/` — pytest tests

## Scripts

All scripts require the package to be installed: `uv pip install -e .`

### fetch_all.py (recommended)

Runs all ingestion scripts in the correct order. Items must be populated first since other scripts reference the items table.

```sh
uv run python scripts/fetch_all.py [--db data/ragger.db] [--league Raging_Echoes_League/Tasks]
```

### Individual scripts

Pipeline order (managed by `fetch_all.py`):

1. `fetch_items.py` — Pulls all item names from Category:Items
2. `fetch_equipment.py` — Pulls equipment stats (bonuses, slot, speed, combat style) and metadata from Category:Equipment (batched)
3. `fetch_quests.py` — Pulls quests with points, XP/item rewards, skill/quest/QP requirements
4. `fetch_quest_regions.py` — Parses `leagueRegion` infobox field to map quests to regions
5. `fetch_diary_tasks.py` — Pulls diary tasks with skill and quest requirements
6. `fetch_diary_items.py` — Pulls diary task item requirements from Achievement Diary page
7. `fetch_shops.py` — Pulls shop data with items, stock, pricing, and shop type from Category:Shops
8. `fetch_locations.py` — Pulls locations with adjacency graph, region, and map coordinates from Category:Locations
9. `fetch_facilities.py` — Pulls facility coordinates (banks, furnaces, anvils, altars, spinning wheels, looms)
10. `fetch_monsters.py` — Pulls monsters with full stat blocks, spawn locations, and drop tables from Category:Monsters (batched)
11. `fetch_dungeon_entrances.py` — Extracts surface-to-underground entrance/exit map links from location pages
12. `fetch_fairy_rings.py` — Parses fairy ring codes and coordinates, creates links between all 55 codes
13. `fetch_quetzal.py` — Parses Quetzal Transport System stops and creates links between all stops
14. `fetch_charter_ships.py` — Parses charter ship dock coordinates from Trader Stan's Trading Post
15. `fetch_magic_teleports.py` — Parses all spellbook teleports (Standard, Ancient, Lunar) and item teleports (jewellery, etc.)
16. `fetch_activities.py` — Pulls activities/minigames with type, coordinates, skills bitmask, and region from Category:Activities
17. `fetch_npcs.py` — Pulls non-combat NPC data (name, version, location, options, region) from Category:Non-player characters
18. `fetch_recipes.py` — Pulls item recipes from all pages using {{Recipe}} template (skills, inputs, outputs, tools, ticks, facilities)
19. `fetch_wiki_vars.py` — Scrapes RuneScape:Varplayer/* and RuneScape:Varbit/* wiki pages for descriptions, content links, var class, and value annotations (quest stages, etc.)
20. `link_shop_locations.py` — Links shops to locations by matching location text
21. `link_activity_locations.py` — Links activities to locations by matching location text
22. `link_facilities.py` — Derives facility bitmasks on locations from nearest facility coordinates
23. `compute_walkability.py` — Computes walkable connections via Voronoi edge flood fill and map tile collision data. Supports `--area-threshold`, `--edge-samples`, `--resolution`, `--debug` flags.

### Utility scripts

- `import_map_squares.py` — Imports map square images from `data/map-squares.zip` into the `map_squares` table. One-time setup.
- `import_game_vars.py` — Imports game var JSON from `data/game-vars/` (produced by `dumpGameVariables`) into the `game_vars` table. Re-run after updating RuneLite.
- `classify_game_vars.py` — Classifies game variable names using Claude CLI. Tags vars with content categories and functional tags. Supports `--workers`, `--batch-size`, `--session-reset`, `--model`, `--reclassify` flags.
- `fetch_league_tasks.py` — Pulls league tasks (with `--league` flag)

## Cache Dump Tool

Java tool in `tools/cache-dump/` that extracts map data and game constants from the OSRS game cache and RuneLite API. Automatically downloads the latest cache from [OpenRS2](https://archive.openrs2.org/).

Requires JDK 21+. Run from `tools/cache-dump/`:

```sh
# Dump collision maps (red = blocked, white = walkable)
./gradlew dumpCollision [--args="--plane 0 --output ../../data/cache-dump/collision"]

# Dump water masks (blue = water, transparent = land)
./gradlew dumpWater [--args="--plane 0 --output ../../data/cache-dump/water"]

# Dump rendered map tiles (terrain + walls, no objects/icons)
./gradlew dumpMapTiles [--args="--objects --icons --no-walls"]

# Dump game variable constants (varps, varbits, varcs) to JSON
./gradlew dumpGameVariables [--args="--output ../../data/game-vars"]
```

Output: `data/cache-dump/{collision,water,map-tiles}/{plane}_{rx}_{ry}.png`
Output: `data/game-vars/{varp,varbit,varc_int}.json`

### DumpMapTiles flags

| Flag | Default | Description |
|------|---------|-------------|
| `--walls` / `--no-walls` | on | Wall outlines |
| `--overlays` / `--no-overlays` | on | Overlay textures (paths, floors) |
| `--objects` / `--no-objects` | off | Trees, rocks, buildings, scenery |
| `--icons` / `--no-icons` | off | Map icons (bank, altar, etc.) |
| `--labels` / `--no-labels` | off | Text labels |
| `--transparent` | off | Transparent background |
| `--plane N` | 0 | Which plane to render |

All tools accept `--cache <path>` to use a local cache directory instead of downloading.

### release.py

Creates a GitHub release with the database, map squares, and CREDITS.md attached. Auto-commits updated CREDITS.md before tagging.

```sh
uv run python scripts/release.py [version] [--notes "..."]
```

Version defaults to the `VERSION` file.

All fetch scripts share utilities from `src/ragger/wiki.py` (API constants, category enumeration, wikitext fetching, template parsing, requirement linking, attribution).

### Attribution

All scripts that fetch wiki data **must** record attributions. Use `record_attributions_batch()` for scripts that fetch many pages (batches contributor lookups 50 pages per API call) or `fetch_page_wikitext_with_attribution()` for single-page fetches. Attributions are stored in the `attributions` table and used to generate CREDITS.md on release.

### API etiquette

- Default throttle is 1 request/second (override locally via `RAGGER_THROTTLE` in `.env`)
- Prefer batched API calls where possible — `fetch_contributors_batch()` handles up to 50 pages per call
- User-Agent includes project URL per wiki API policy
- Wikitext must be fetched one page at a time (`action=parse`), but contributor lookups support batching (`action=query`)

## Database

Default path: `data/ragger.db`. All scripts accept `--db` to override.

Tables are created automatically when any script runs. Only `fetch_items.py` writes to the items table — all other scripts reference it.

## Python API

All API methods accept a `sqlite3.Connection` so connections can be reused.

### Quest (`src/ragger/quest.py`)

```python
from ragger.quest import Quest

Quest.all(conn) -> list[Quest]
Quest.by_name(conn, name) -> Quest | None
quest.xp_rewards(conn) -> list[ExperienceReward]
quest.item_rewards(conn) -> list[ItemReward]
quest.skill_requirements(conn) -> list[SkillRequirement]
quest.quest_requirements(conn) -> list[QuestRequirement]
quest.quest_point_requirement(conn) -> QuestPointRequirement | None
quest.requirement_chain(conn) -> list[Quest]       # flat list, bottom-up order
quest.requirement_tree(conn) -> str                 # indented tree string
quest.game_vars(conn) -> list[GameVariable]             # associated game variables
```

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

### Equipment (`src/ragger/equipment.py`)

```python
from ragger.equipment import Equipment

Equipment.all(conn, slot?) -> list[Equipment]
Equipment.by_name(conn, name, version?) -> Equipment | None
Equipment.by_slot(conn, slot) -> list[Equipment]
Equipment.search(conn, name) -> list[Equipment]
Equipment.for_item(conn, item_id) -> list[Equipment]
equipment.slot -> EquipmentSlot | None
equipment.two_handed -> bool                           # True for 2h weapons
equipment.combat_style -> CombatStyle | None
equipment.item_id -> int | None                        # FK to items table
# Attack bonuses: attack_stab, attack_slash, attack_crush, attack_magic, attack_ranged
# Defence bonuses: defence_stab, defence_slash, defence_crush, defence_magic, defence_ranged
# Other bonuses: melee_strength, ranged_strength, magic_damage, prayer
# Weapon-only: speed, attack_range, combat_style
```

### DiaryTask (`src/ragger/diary.py`)

```python
from ragger.diary import DiaryTask

DiaryTask.all(conn, location?, tier?) -> list[DiaryTask]
```

Diary XP rewards are on the enum: `DiaryLocation.xp_reward(tier)` and `DiaryLocation.min_level(tier)`.

### LeagueTask (`src/ragger/league.py`)

```python
from ragger.league import LeagueTask

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

### Shop (`src/ragger/shop.py`)

```python
from ragger.shop import Shop, ShopItem

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

### Location (`src/ragger/location.py`)

```python
from ragger.location import Location, DistanceMetric

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
location.game_vars(conn) -> list[GameVariable]          # associated game variables
```

Distance metrics for `nearby()` and `nearest()`: `DistanceMetric.CHEBYSHEV` (default, matches OSRS diagonal movement), `DistanceMetric.MANHATTAN`, `DistanceMetric.EUCLIDEAN`. Distance computation is on the enum: `metric.compute(dx, dy)`.

### FacilityEntry (`src/ragger/facility.py`)

Raw facility coordinate data (banks, furnaces, anvils, altars, spinning wheels, looms).

```python
from ragger.facility import FacilityEntry
from ragger.enums import Facility

FacilityEntry.all(conn, facility_type?, region?) -> list[FacilityEntry]
FacilityEntry.nearest(conn, x, y, facility_type?, metric?) -> FacilityEntry | None
FacilityEntry.nearby(conn, x, y, max_distance, facility_type?, metric?) -> list[tuple[FacilityEntry, float]]
entry.type -> Facility
entry.x -> int
entry.y -> int
entry.name -> str | None
entry.region -> Region | None                          # derived from nearest location
```

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

MapSquare.get(conn, plane, region_x, region_y) -> MapSquare | None
MapSquare.all(conn, plane=0) -> list[MapSquare]
MapSquare.at_game_coord(conn, x, y, plane=0) -> MapSquare | None
MapSquare.count(conn, plane=0) -> int
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

### Recipe (`src/ragger/recipe.py`)

```python
from ragger.recipe import Recipe, RecipeSkill, RecipeInput, RecipeOutput, RecipeTool

Recipe.all(conn) -> list[Recipe]
Recipe.by_name(conn, name) -> list[Recipe]             # multiple methods for same output
Recipe.by_skill(conn, skill) -> list[Recipe]           # recipes using a specific skill
Recipe.for_item(conn, item_name) -> list[Recipe]       # recipes that produce an item
Recipe.using(conn, item_name) -> list[Recipe]          # recipes that consume an item as input
Recipe.at_facility(conn, facility) -> list[Recipe]     # recipes requiring a facility
Recipe.search(conn, name) -> list[Recipe]              # partial name match
recipe.skills(conn) -> list[RecipeSkill]               # skill requirements and XP
recipe.inputs(conn) -> list[RecipeInput]               # consumed materials
recipe.outputs(conn) -> list[RecipeOutput]             # produced items (only resolved items)
recipe.tools(conn) -> list[RecipeTool]                 # non-consumed tools
recipe.name -> str                                     # what the recipe creates
recipe.members -> bool
recipe.ticks -> int | None                             # game ticks per action
recipe.notes -> str | None                             # quest/other requirements
recipe.facilities -> str | None                        # required facility (Furnace, Anvil, etc.)

# RecipeTool.tool_group groups alternatives: all groups are AND'd together;
# items within the same group are OR'd.
# E.g. group 0: Knife AND group 1: (Air tiara OR Air talisman)
```

### Npc (`src/ragger/npc.py`)

```python
from ragger.npc import Npc

Npc.all(conn, region?) -> list[Npc]
Npc.by_name(conn, name) -> list[Npc]              # multiple versions possible
Npc.search(conn, name) -> list[Npc]                # partial name match
Npc.with_option(conn, option, region?) -> list[Npc] # e.g. "Travel", "Teleport"
Npc.at_location(conn, location) -> list[Npc]
npc.has_option(option) -> bool
npc.option_list() -> list[str]
npc.game_vars(conn) -> list[GameVariable]               # associated game variables
```

### Monster (`src/ragger/monster.py`)

```python
from ragger.monster import Monster, MonsterLocation, MonsterDrop

Monster.all(conn, region?) -> list[Monster]
Monster.by_name(conn, name, version?) -> Monster | None
Monster.by_slayer_category(conn, category) -> list[Monster]
Monster.search(conn, name) -> list[Monster]            # partial name match
monster.locations(conn) -> list[MonsterLocation]
monster.drops(conn) -> list[MonsterDrop]
monster.drops_by_name(conn, item_name) -> list[MonsterDrop]
monster.has_immunity(immunity) -> bool
monster.immunity_list() -> list[Immunity]
monster.game_vars(conn) -> list[GameVariable]           # associated game variables
monster.combat_level -> int | None
monster.hitpoints -> int | None
monster.immunities -> int                              # bitmask
monster.slayer_category -> str | None
monster.elemental_weakness_type -> str | None
monster.elemental_weakness_percent -> int | None
# Full stat block: attack/strength/defence/magic/ranged levels and bonuses
# Full defensive bonuses: stab/slash/crush/magic/light/standard/heavy ranged
```

### GameVariable (`src/ragger/game_variable.py`)

```python
from ragger.game_variable import GameVariable, ContentTag
from ragger.enums import ContentCategory, FunctionalTag

GameVariable.all(conn, var_type?) -> list[GameVariable]       # var_type: VariableType enum
GameVariable.by_name(conn, name) -> list[GameVariable]        # exact name match
GameVariable.search(conn, name) -> list[GameVariable]         # partial name match (LIKE %name%)
GameVariable.by_var_id(conn, var_id, var_type) -> GameVariable | None
GameVariable.by_content_tag(conn, ContentCategory.QUEST, "dragon_slayer_i") -> list[GameVariable]  # enum + name
GameVariable.by_content_tag(conn, "quest:dragon_slayer_i") -> list[GameVariable]                  # legacy string form
GameVariable.by_content_tag(conn, ContentCategory.QUEST) -> list[GameVariable]                    # all vars in category
GameVariable.by_functional_tag(conn, tag, var_type?) -> list[GameVariable]    # FunctionalTag.TIMER or "timer"
var.name -> str                                     # client name hash (e.g. "COM_STANCE")
var.var_id -> int                                   # numeric ID to pass to varp:get/varc:int
var.var_type -> VariableType                         # VARP, VARBIT, VARC_INT, VARC_STR
var.description -> str | None                       # human-readable description (if annotated)
var.content_tags -> list[ContentTag]                # e.g. [ContentTag(QUEST, "troll_stronghold")]
var.functional_tags -> list[FunctionalTag]          # e.g. [FunctionalTag.PROGRESS]
var.wiki_name -> str | None                         # wiki-documented name (e.g. "DRAGON_SLAYER_I_PROGRESS")
var.wiki_content -> str | None                      # wiki-linked content (e.g. "Dragon Slayer I")
var.var_class -> str | None                         # Enum, Switch, Counter, Bitmap, Other
var.values(conn) -> list[VariableValue]                  # annotated values (e.g. quest stages)

# VariableValue fields
vv.var_type -> str
vv.var_id -> int
vv.value -> int                                     # e.g. 0, 1, 2
vv.label -> str                                     # e.g. "Not started", "Started", "Completed"

# ContentTag fields
tag.category -> ContentCategory                     # QUEST, SKILL, NPC, LOCATION, ITEM, MINIGAME, ACTIVITY
tag.name -> str                                     # e.g. "troll_stronghold"
str(tag) -> "quest:troll_stronghold"
```

### Wiki utilities (`src/ragger/wiki.py`)

```python
from ragger.wiki import (
    fetch_category_members,
    fetch_page_wikitext,
    fetch_pages_wikitext_batch,
    fetch_page_wikitext_with_attribution,
    fetch_contributors_batch,
    record_attribution,
    record_attributions_batch,
    strip_markup,
    strip_wiki_links,
    extract_template,
    extract_section,
    parse_template_param,
    parse_skill_requirements,
    link_requirement,
    throttle,
)

# Fetching
fetch_category_members(category, ...) -> list[str]                         # paginated category listing
fetch_page_wikitext(page) -> str                                           # raw wikitext for one page
fetch_pages_wikitext_batch(pages) -> dict[str, str]                        # batch fetch up to 50 pages
fetch_page_wikitext_with_attribution(conn, page, table_name) -> str        # wikitext + record attribution
fetch_contributors_batch(pages) -> dict[str, list[str]]                    # contributors for up to 50 pages

# Attribution (required for all data ingestion)
record_attribution(conn, table_name, wiki_page, authors)                   # single page
record_attributions_batch(conn, table_names, pages)                        # batched; table_names can be str or list[str]

# Parsing
strip_markup(text) -> str                                                  # remove wiki markup
strip_wiki_links(text) -> str                                              # [[Link|Display]] -> Display
extract_template(wikitext, template_name) -> str | None                    # nested brace-aware
extract_section(wikitext, field_name) -> str                               # |field= section
parse_template_param(text, param) -> str | None                            # single param
parse_skill_requirements(text) -> list[tuple[int, int]]                    # {{SCP|Skill|Level}}

# DB helpers
link_requirement(conn, table, columns, junction_table, ...)                # insert-or-ignore + link
throttle()                                                                 # rate limit (default 1s)
```

## Enums (`src/ragger/enums.py`)

- `Skill(int, Enum)` — 23 OSRS skills, int-based with `label`, `mask` properties
- `Region(int, Enum)` — 12 regions (including GENERAL), int-based with `label`, `mask`, `from_label` properties
- `TaskDifficulty(int, Enum)` — Easy/Medium/Hard/Elite/Master with `label`, `points` properties
- `DiaryLocation(str, Enum)` — 12 diary regions with `xp_reward(tier)`, `min_level(tier)` methods
- `DiaryTier(str, Enum)` — Easy/Medium/Hard/Elite
- `EquipmentSlot(str, Enum)` — 11 equipment slots (head, weapon, body, legs, shield, cape, hands, feet, neck, ammo, ring) with `label`, `from_label` (maps wiki `2h` to `WEAPON`)
- `CombatStyle(str, Enum)` — 28 weapon combat styles (2h Sword, Axe, Bow, Crossbow, Slash Sword, Staff, Whip, etc.) with `from_label`
- `ShopType(str, Enum)` — 36 shop types (General, Gem, Fishing, Magic, etc.) with `from_label` fuzzy matching
- `ActivityType(str, Enum)` — Minigame, Random event, Forestry, Raid, Activity, Boss, Distraction and Diversion, Quest, Reward with `from_label` (falls back to Activity)
- `VariableType(str, Enum)` — varp, varbit, varc_int, varc_str with `from_label`
- `ContentCategory(str, Enum)` — quest, skill, npc, location, item, minigame, activity with `from_label`
- `FunctionalTag(str, Enum)` — progress, toggle, counter, ui, config, storage, timer, cosmetic with `from_label`
- `Facility(int, Enum)` — Bank, Furnace, Anvil, Range, Altar, Spinning wheel, Loom with `mask`, `label` properties
- `Immunity(int, Enum)` — Poison, Venom, Cannon, Thrall, Burn with `mask`, `label` properties
- `MapLinkType(str, Enum)` — entrance, exit, fairy_ring, charter_ship, spirit_tree, gnome_glider, canoe, teleport, minecart, ship, quetzal, walkable, npc_transport
- `MAP_LINK_ANYWHERE` — constant `"ANYWHERE"` for teleport from_location (castable from any location)
- `ALL_SKILLS_MASK`, `ALL_REGIONS_MASK` — bitmask constants for "all"
- `COMBAT_SKILLS_MASK` — bitmask for Attack, Strength, Defence, Hitpoints, Ranged, Magic, Prayer

## RuneLite Plugin

Java plugin in `plugin/` that embeds an AI assistant into the RuneLite client. In-game console overlay (toggle with backtick) talks to Claude CLI. Lua actor engine (luajava/LuaJ) for dynamic client modifications. HTTP bridge server for MCP tool communication.

Requires JDK 21+. Run from `plugin/`:

```sh
./run.sh                    # launches RuneLite with the plugin loaded
```

Or manually:

```sh
JAVA_HOME="$(brew --prefix openjdk@21)/libexec/openjdk.jdk/Contents/Home" ./gradlew run
```

### Plugin structure

- `RaggerPlugin.java` — main plugin entry, overlay registration, game tick dispatch, input handling
- `RaggerConfig.java` — plugin config (Claude CLI path, model, bridge port)
- `ClaudeClient.java` — spawns Claude CLI with behavior prompts, parses stream-json responses
- `ClaudeResponse.java` — parsed response with text, actors, and tool log
- `BridgeServer.java` — HTTP server on localhost for MCP tool bridge (eval/run endpoints)
- `ui/ChatPanel.java` — minimal sidebar panel (hint label)
- `ui/ConsoleOverlay.java` — in-game console overlay with markdown rendering
- `scripting/ActorManager.java` — Lua actor lifecycle manager
- `scripting/LuaActor.java` — single Lua actor instance with API bindings and lifecycle hooks
- `scripting/ActorOverlay.java` — overlay that dispatches render calls to active actors
- `scripting/ChatApi.java` — Lua `chat` API (game messages, console messages)
- `scripting/CameraApi.java` — Lua `camera` API (position, angles, controls)
- `scripting/ClientApi.java` — Lua `client` API (world, state, viewport, FPS)
- `scripting/PlayerApi.java` — Lua `player` API (stats, position, HP, prayer)
- `scripting/SkillApi.java` — Lua `skill` enum constants
- `scripting/SceneApi.java` — Lua `scene` API (NPCs, players, ground items)
- `scripting/CoordsApi.java` — Lua `coords` API (world/local/canvas coordinate projection)
- `scripting/ItemsApi.java` — Lua `items` API (GE prices, HA values, item lookups)
- `scripting/InventoryApi.java` — Lua `inventory` API (inventory items, equipment)
- `scripting/CombatApi.java` — Lua `combat` API (spec, prayers, attack style, target)
- `scripting/PrayerApi.java` — Lua `prayer` enum constants
- `scripting/WidgetApi.java` — Lua `widget` API (game interface/widget state, InterfaceID constants)
- `scripting/UiApi.java` — Lua `ui` API (create native HUD panels with text, buttons, sprites, items)
- `scripting/UiPanel.java` — panel state and widget tree tracking
- `scripting/UiElement.java` — element state and callback ref tracking
- `scripting/VarApi.java` — Lua `varp`/`varc` APIs (player variables, varbits, client variables)
- `scripting/OverlayApi.java` — Lua overlay drawing context (text, shapes, fonts)
- `scripting/MailApi.java` — Lua `mail` API (inter-actor messaging)
- `scripting/MailMessage.java` — mail message data object
- `scripting/ActorsApi.java` — Lua `actors` API (child actor management, templates)
- `scripting/JsonApi.java` — Lua `json` API (encode/decode)
- `scripting/Base64Api.java` — Lua `base64` API (encode/decode)
- `scripting/LuaUtils.java` — shared Lua conversion utilities
- `scripting/ServiceManager.java` — managed service lifecycle and watchdog

### MCP Server

Python MCP server at `src/ragger/mcp_server.py` exposes the following tools:

- `RaggerActorSpawn(name, script)` — submit a persistent Lua actor to the plugin
- `RaggerEval(script)` — evaluate a Lua expression and return the result
- `RaggerActorList()` — list active actors
- `RaggerActorSource(name)` — retrieve a running actor's source code
- `RaggerTemplateList()` — list registered templates
- `RaggerTemplateSource(name)` — retrieve a template's source code
- `RaggerMailSend(name, messages)` — send one or more messages to a single actor's `on_mail` hook
- `RaggerMailSendBatch(messages)` — send messages to multiple actors in one call
- `RaggerMailRecvAsync(limit?, from_actor?)` — non-blocking read of messages sent to Claude
- `RaggerMailRecvSync(count?, from_actor?, timeout?)` — blocking read, waits for messages

All tools bridge through the plugin's HTTP server on localhost (default port 7919). Per-session auth token prevents unauthorized access.

### Behaviors

System prompts are embedded as classpath resources in `src/main/resources/dev/ragger/plugin/`:

- `BASE.md` — core identity, rules, and full Lua API reference
- `ASSISTANT.md` — OSRS Q&A mode

Behaviors are appended to every Claude CLI invocation via `--append-system-prompt`.

### Console Commands

- `/reset` — reset Claude session and clear console
- `/clear` — clear console output (keep session)
- `/stop` — stop all running actors
- `/stop <name>` — stop a specific actor
- `/actors` — list active actors
- `/services` — list service status
- `/revive <name>` — reset a dead service

## Tests

```sh
uv run pytest
```
