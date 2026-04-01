import sqlite3
from pathlib import Path

from clogger.enums import Region
from clogger.league import LeagueConfig


def _seed_quests(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO quests (name, points, autocompleted) VALUES (?, ?, ?)",
        [
            ("Dragon Slayer I", 2, 1),
            ("Lost City", 3, 1),
            ("Priest in Peril", 1, 1),
            ("Monkey Madness I", 3, 0),
            ("Desert Treasure I", 3, 0),
        ],
    )
    conn.commit()


def test_from_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "test.yaml"
    config_path.write_text(
        """
starting_region: Varlamore
always_accessible:
  - Varlamore
  - Karamja
unlockable_regions:
  - Asgarnia
  - Kandarin
max_region_unlocks: 3
autocompleted_quests:
  - Dragon Slayer I
  - Lost City
"""
    )
    config = LeagueConfig.from_yaml(config_path)
    assert config.starting_region == Region.VARLAMORE
    assert config.always_accessible == [Region.VARLAMORE, Region.KARAMJA]
    assert Region.ASGARNIA in config.unlockable_regions
    assert config.max_region_unlocks == 3
    assert len(config.autocompleted_quests) == 2


def test_completed_quests(conn: sqlite3.Connection) -> None:
    _seed_quests(conn)
    config = LeagueConfig(
        starting_region=Region.VARLAMORE,
        always_accessible=[Region.VARLAMORE, Region.KARAMJA],
        unlockable_regions=[],
        max_region_unlocks=3,
        autocompleted_quests=[],
    )
    completed = config.completed_quests(conn)
    assert len(completed) == 3
    assert all(q.autocompleted for q in completed)


def test_starting_quest_points(conn: sqlite3.Connection) -> None:
    _seed_quests(conn)
    config = LeagueConfig(
        starting_region=Region.VARLAMORE,
        always_accessible=[],
        unlockable_regions=[],
        max_region_unlocks=0,
        autocompleted_quests=[],
    )
    assert config.starting_quest_points(conn) == 6  # 2 + 3 + 1


def test_available_regions() -> None:
    config = LeagueConfig(
        starting_region=Region.VARLAMORE,
        always_accessible=[Region.VARLAMORE, Region.KARAMJA],
        unlockable_regions=[Region.ASGARNIA, Region.KANDARIN, Region.MORYTANIA],
        max_region_unlocks=3,
        autocompleted_quests=[],
    )
    assert config.available_regions() == [Region.VARLAMORE, Region.KARAMJA]
    assert config.available_regions([Region.ASGARNIA]) == [Region.VARLAMORE, Region.KARAMJA, Region.ASGARNIA]
    # Can't unlock a region not in unlockable list
    assert config.available_regions([Region.WILDERNESS]) == [Region.VARLAMORE, Region.KARAMJA]
