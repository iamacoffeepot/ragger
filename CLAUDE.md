# Ragger

OSRS knowledge base powered by retrieval-augmented generation.

## Project Structure

- `src/ragger/` — Python package with data models and database module
- `scripts/` — Top-level orchestration (fetch_all.py, release.py, classify_game_vars.py)
- `scripts/pipeline/` — Data pipeline scripts (wiki fetch, linking, compute)
- `scripts/import/` — One-time local data imports (map squares, game vars)
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

### Pipeline scripts (`scripts/pipeline/`)

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
18. `fetch_npc_locations.py` — Associates NPC game IDs with wiki-stated coordinates by parsing versioned id and map fields from Infobox NPC
19. `fetch_actions.py` — Universal action ingestion from {{Skill table}} templates. One API call per skill expands the table and parses name, level, XP, materials, tools, facilities, and secondary skills. Entity/facility pages are batch-fetched for Infobox NPC/Scenery game IDs, with ops resolved from cache dump definitions. Replaces all individual fetch_*_actions.py scripts and trigger linking scripts. Supports `--skill` to run a single skill.
20. `fetch_wiki_vars.py` — Scrapes RuneScape:Varplayer/* and RuneScape:Varbit/* wiki pages for descriptions, content links, var class, and value annotations (quest stages, etc.)
21. `fetch_dialogues.py` — Pulls dialogue trees from Transcript: pages (namespace 120). Parses *-indented wikitext with {{topt}}, {{tcond}}, {{tact}}, {{tbox}}, {{tselect}}, {{qact}} templates into an adjacency-list tree in dialogue_pages + dialogue_nodes.
23. `link_shop_locations.py` — Links shops to locations by matching location text
24. `link_activity_locations.py` — Links activities to locations by matching location text
25. `link_facilities.py` — Derives facility bitmasks on locations from nearest facility coordinates
26. `compute_dialogue_tags.py` — Aho-Corasick entity tagging over dialogue nodes. Matches items, NPCs, monsters, quests, locations, shops, equipment, and activities. Stores probable links in dialogue_tags.
27. `link_npc_dialogues.py` — Links NPCs to dialogue pages by exact name match on npc-type transcripts
28. `link_quest_dialogues.py` — Links quests to dialogue pages by exact name match on quest-type transcripts
29. `compute_walkability.py` — Computes walkable connections via Voronoi edge flood fill and map tile collision data. Supports `--area-threshold`, `--edge-samples`, `--resolution`, `--debug` flags.

### Import scripts (`scripts/import/`)

- `import_map_squares.py` — Imports map square images from `data/map-squares.zip` into the `map_squares` table. One-time setup.
- `import_game_vars.py` — Imports game var JSON from `data/game-vars/` (produced by `dumpGameVariables`) into the `game_vars` table. Re-run after updating RuneLite.
- `import_object_locations.py` — Imports interactive object spawn locations from `data/cache-dump/object-locations.json` (produced by `dumpObjectLocations`) into the `object_locations` table.

### Utility scripts

- `classify_game_vars.py` — Classifies game variable names using Claude CLI. Tags vars with content categories and functional tags. Supports `--workers`, `--batch-size`, `--session-reset`, `--model`, `--reclassify` flags.
- `validate_wiki_cache.py` — Bulk-validates wiki cache revids against current wiki state. Bumps `fetched_at` on fresh entries, evicts stale ones. Run before ingestion to avoid per-page revid checks. Supports `--cache` flag.

`fetch_league_tasks.py` is in `scripts/pipeline/` but run separately via `fetch_all.py --league`.

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

# Dump NPC definitions (id, name, size, combatLevel, ops, conditionalOps) to JSON
./gradlew dumpNpcDefinitions [--args="--output ../../data/cache-dump/npc-definitions.json"]

# Dump object definitions (id, name, sizeX, sizeY, ops, conditionalOps) to JSON
./gradlew dumpObjectDefinitions [--args="--output ../../data/cache-dump/object-definitions.json"]

# Dump interactive object spawn locations (objects with menu ops) to JSON
./gradlew dumpObjectLocations [--args="--output ../../data/cache-dump/object-locations.json"]
```

Output: `data/cache-dump/{collision,water,map-tiles}/{plane}_{rx}_{ry}.png`
Output: `data/cache-dump/{npc,object}-definitions.json`
Output: `data/cache-dump/object-locations.json`
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
- Wiki page cache: set `RAGGER_WIKI_CACHE=data/wiki-cache.db` to cache wikitext in a separate SQLite database. Cache entries within the TTL (default 24 hours, override with `RAGGER_WIKI_TTL` in seconds) are trusted without revid checks. Stale entries are re-validated via a cheap revid-only API call. Run `scripts/validate_wiki_cache.py` to bulk-validate all cached revids and reset their TTL. `WikiCache` class can also be passed directly to fetch functions via the `cache` parameter.

## Database

Default path: `data/ragger.db`. All scripts accept `--db` to override.

Tables are created automatically when any script runs. Only `fetch_items.py` writes to the items table — all other scripts reference it.

## Python API

All API methods accept a `sqlite3.Connection` so connections can be reused. Per-module API docs in `docs/api/`:

- `QUEST.md` — Quest with rewards, requirements, requirement chains
- `ITEM.md` — Item lookup by name, game ID, search
- `EQUIPMENT.md` — Equipment stats, slots, combat styles
- `REQUIREMENTS.md` — Shared requirement system (AND groups, OR within)
- `DIARY.md` — DiaryTask with requirements
- `LEAGUE.md` — LeagueTask, LeagueConfig, Account progression
- `SHOP.md` — Shop with items, pricing, multipliers
- `LOCATION.md` — Location with adjacency, facilities, distance metrics
- `FACILITY.md` — FacilityEntry coordinates (banks, furnaces, etc.)
- `MAP.md` — MapLink, MapSquare, pathfinding (A* with Chebyshev)
- `ACTIVITY.md` — Activity/minigame lookup
- `ACTION.md` — Action with inputs, outputs, requirements, triggers
- `NPC.md` — Non-combat NPC lookup, NpcLocation (game ID to coordinates)
- `DIALOGUE.md` — DialoguePage, DialogueNode (tree traversal, subtree CTE), DialogueTag (entity tagging)
- `OBJECT.md` — ObjectLocation (interactive object spawns by game ID and coordinates)
- `MONSTER.md` — Monster stats, locations, drops, immunities
- `GAME_VARIABLE.md` — GameVariable with content/functional tags, values
- `WIKI.md` — Wiki fetch, parse, cache, attribution utilities
- `ENUMS.md` — All enums (Skill, Region, EquipmentSlot, MapLinkType, etc.)

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
