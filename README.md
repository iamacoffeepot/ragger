# Ragger

OSRS knowledge base powered by retrieval-augmented generation. Built with [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

Pulls data from the [OSRS Wiki](https://oldschool.runescape.wiki/) and the game cache into a SQLite database. Python API for querying quests, items, diary tasks, league tasks, shops, locations, monsters, NPCs, game variables, and map data with pathfinding. RuneLite plugin with an AI chat console and Lua actor engine for live client modifications.

## Prerequisites

- [Python 3.12+](https://www.python.org/)
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (CLI for Claude)
- [JDK 21+](https://openjdk.org/) (for RuneLite plugin and cache dump tool)

## Getting started

### 1. Clone and install

```sh
git clone https://github.com/iamacoffeepot/ragger.git
cd ragger
uv pip install -e .
```

### 2. Get the database

Download `ragger.db` from the [latest release](https://github.com/iamacoffeepot/ragger/releases) and place it in `data/`:

```sh
mkdir -p data
gh release download --pattern "ragger.db" --dir data
```

Or populate it yourself from the wiki (takes a while due to API rate limiting):

```sh
uv run python scripts/fetch_all.py --league Raging_Echoes_League/Tasks
```

### 3. Start Claude Code

```sh
claude
```

Claude reads [CLAUDE.md](CLAUDE.md) automatically and knows the full API. You can ask it things like:

- "What shops are in Varlamore?"
- "What tasks require Crafting?"
- "What's within 3 hops of Civitas illa Fortis?"
- "Where are the banks near Aldarin?"
- "What quests can I do with 50 Attack and access to Morytania?"

Claude will use the Python API to query the database and answer without you needing to write any code.

### 4. RuneLite plugin

An AI assistant embedded in the RuneLite client. In-game console overlay (toggle with backtick) talks to Claude — ask about quests, items, strategies, or have it write Lua actors that modify the client in real time (tile markers, NPC highlights, timers, loot tracking, custom overlays). Requires JDK 21+.

```sh
cd plugin
./run.sh
```

This launches RuneLite with the Ragger plugin pre-loaded. The plugin includes:

- **Lua actor engine** — sandboxed scripts with access to scene, inventory, combat, widget, and coordinate APIs
- **Built-in services** — tile markers, NPC highlights, timers, loot tracker, stat tracker, radar (managed by a watchdog, controlled via mail)
- **MCP bridge** — Claude can spawn actors, evaluate expressions, and send/receive mail through MCP tools

### 5. Cache dump tool (optional)

Extracts collision maps, water masks, rendered map tiles, and game variable constants from the OSRS game cache. Requires JDK 21+.

```sh
cd tools/cache-dump
./gradlew dumpCollision   # collision flags
./gradlew dumpWater       # water masks
./gradlew dumpMapTiles    # rendered terrain tiles
./gradlew dumpGameVars    # varp/varbit/varc constants to JSON
```

The tool automatically downloads the latest OSRS cache from [OpenRS2](https://archive.openrs2.org/). Output goes to `data/cache-dump/` and `data/game-vars/`.

### 6. Classify game variables (optional)

Tags the 18K game variables in the database with content and functional metadata using Claude via the CLI:

```sh
uv run python scripts/classify_game_vars.py --limit 100 --dry-run  # preview
uv run python scripts/classify_game_vars.py                         # full run
```

Uses Sonnet by default. The prompt is seeded with real entity names from the database and a hardcoded abbreviation map for known var name prefixes. Content tags are validated against quests, items, NPCs, and locations in the DB.

## Running tests

```sh
uv run pytest
```

## API reference

See [CLAUDE.md](CLAUDE.md) for the full Python API documentation.

## Data attribution

All game data is sourced from the [Old School RuneScape Wiki](https://oldschool.runescape.wiki/), which is licensed under [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/). The database distributed in releases contains content from wiki contributors — see the [wiki's copyright page](https://oldschool.runescape.wiki/w/RuneScape:Copyrights) for details.

Old School RuneScape is a registered trademark of Jagex Ltd.

## License

Code is licensed under [MIT](LICENSE). Database contents are subject to the OSRS Wiki's [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/) license.
