# Ragger

OSRS knowledge base powered by retrieval-augmented generation. Built with [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

Pulls data from the [OSRS Wiki](https://oldschool.runescape.wiki/) and the game cache into a SQLite database and provides a Python API for querying quests, items, diary tasks, league tasks, shops, locations, monsters, NPCs, and map data — everything you need to plan, pathfind, and theorycraft without writing SQL.

## Prerequisites

- [Python 3.12+](https://www.python.org/)
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (CLI for Claude)
- [JDK 21+](https://adoptium.net/) (optional, for cache dump tool)

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

### 4. Cache dump tool (optional)

Extracts collision maps, water masks, and rendered map tiles from the OSRS game cache. Requires JDK 21+.

```sh
cd tools/cache-dump
./gradlew dumpCollision   # collision flags
./gradlew dumpWater       # water masks
./gradlew dumpMapTiles    # rendered terrain tiles
```

The tool automatically downloads the latest OSRS cache from [OpenRS2](https://archive.openrs2.org/). Output goes to `data/cache-dump/`.

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
