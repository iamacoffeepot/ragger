import sqlite3
from pathlib import Path

from ragger.enums import Region
from ragger.league import LeagueConfig


def _seed_quests(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO quests (name, points) VALUES (?, ?)",
        [
            ("Quest A", 2),
            ("Quest B", 3),
            ("Quest C", 1),
        ],
    )
    # A requires B
    b_id = conn.execute("SELECT id FROM quests WHERE name = 'Quest B'").fetchone()[0]
    conn.execute(
        "INSERT INTO quest_requirements (required_quest_id, partial) VALUES (?, 0)",
        (b_id,),
    )
    req_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    a_id = conn.execute("SELECT id FROM quests WHERE name = 'Quest A'").fetchone()[0]
    conn.execute(
        "INSERT INTO quest_quest_requirements (quest_id, quest_requirement_id) VALUES (?, ?)",
        (a_id, req_id),
    )
    conn.commit()


def test_from_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "test.yaml"
    config_path.write_text(
        """
starting-region: Varlamore
always-accessible:
  - Varlamore
  - Karamja
unlockable-regions:
  - Asgarnia
  - Kandarin
max-region-unlocks: 3
autocompleted-quests:
  - Quest A
"""
    )
    config = LeagueConfig.from_yaml(config_path)
    assert config.starting_region == Region.VARLAMORE
    assert config.always_accessible == [Region.VARLAMORE, Region.KARAMJA]
    assert Region.ASGARNIA in config.unlockable_regions
    assert config.max_region_unlocks == 3


def test_completed_quests_with_chain(conn: sqlite3.Connection) -> None:
    _seed_quests(conn)
    config = LeagueConfig(
        starting_region=Region.VARLAMORE,
        starting_location="Civitas illa Fortis",
        always_accessible=[],
        unlockable_regions=[],
        max_region_unlocks=0,
        starting_skills={},
        autocompleted_quests=["Quest A"],
    )
    completed = config.completed_quests(conn)
    names = [q.name for q in completed]
    assert "Quest A" in names
    assert "Quest B" in names  # chain dependency
    assert "Quest C" not in names


def test_starting_quest_points(conn: sqlite3.Connection) -> None:
    _seed_quests(conn)
    config = LeagueConfig(
        starting_region=Region.VARLAMORE,
        starting_location="Civitas illa Fortis",
        always_accessible=[],
        unlockable_regions=[],
        max_region_unlocks=0,
        starting_skills={},
        autocompleted_quests=["Quest A"],
    )
    # Quest A (2) + Quest B (3) from chain
    assert config.starting_quest_points(conn) == 5


def test_available_regions() -> None:
    config = LeagueConfig(
        starting_region=Region.VARLAMORE,
        starting_location="Civitas illa Fortis",
        always_accessible=[Region.VARLAMORE, Region.KARAMJA],
        unlockable_regions=[Region.ASGARNIA, Region.KANDARIN, Region.MORYTANIA],
        max_region_unlocks=3,
        starting_skills={},
        autocompleted_quests=[],
    )
    assert config.available_regions() == [Region.VARLAMORE, Region.KARAMJA]
    assert config.available_regions([Region.ASGARNIA]) == [Region.VARLAMORE, Region.KARAMJA, Region.ASGARNIA]
    assert config.available_regions([Region.WILDERNESS]) == [Region.VARLAMORE, Region.KARAMJA]
