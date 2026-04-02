# Clogger

OSRS Leagues knowledge base for route planning. Built with Claude.

Pulls data from the [OSRS Wiki](https://oldschool.runescape.wiki/) into a SQLite database and provides a Python API for querying quests, items, diary tasks, league tasks, shops, locations, and facilities — everything you need to plan a league route without writing SQL.

## Setup

```sh
uv pip install -e .
```

## Populate the database

```sh
uv run python scripts/fetch_all.py --league Raging_Echoes_League/Tasks
```

## Run tests

```sh
uv run pytest
```

## Usage

See [CLAUDE.md](CLAUDE.md) for the full API reference.
