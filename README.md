# Clogger

OSRS Leagues knowledge base for route planning. Built with [Claude Code](https://claude.ai/claude-code).

Pulls data from the [OSRS Wiki](https://oldschool.runescape.wiki/) into a SQLite database and provides a Python API for querying quests, items, diary tasks, league tasks, shops, locations, and facilities — everything you need to plan a league route without writing SQL.

## Prerequisites

- [Python 3.12+](https://www.python.org/)
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Claude Code](https://claude.ai/claude-code) (CLI for Claude)

## Getting started

### 1. Clone and install

```sh
git clone https://github.com/iamacoffeepot/clogger.git
cd clogger
uv pip install -e .
```

### 2. Get the database

Download `clogger.db` from the [latest release](https://github.com/iamacoffeepot/clogger/releases) and place it in `data/`:

```sh
mkdir -p data
gh release download --pattern "clogger.db" --dir data
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

## Running tests

```sh
uv run pytest
```

## API reference

See [CLAUDE.md](CLAUDE.md) for the full Python API documentation.

## License

[MIT](LICENSE)
