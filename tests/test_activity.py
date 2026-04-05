import sqlite3

from ragger.activity import Activity
from ragger.enums import ActivityType, Region, Skill


def _seed_activities(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO activities (name, type, members, location, x, y, players, skills, region) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                "Barbarian Assault",
                ActivityType.MINIGAME.value,
                1,
                "Barbarian Outpost",
                2533, 3571,
                "5",
                Skill.ATTACK.mask | Skill.STRENGTH.mask | Skill.DEFENCE.mask,
                Region.KANDARIN.value,
            ),
            (
                "Fishing Trawler",
                ActivityType.MINIGAME.value,
                1,
                "Port Khazard",
                2667, 3162,
                "1+",
                Skill.FISHING.mask,
                Region.KANDARIN.value,
            ),
            (
                "Beekeeper",
                ActivityType.RANDOM_EVENT.value,
                0,
                None,
                None, None,
                "1",
                0,
                None,
            ),
            (
                "Chambers of Xeric",
                ActivityType.RAID.value,
                1,
                "Mount Quidamortem",
                1255, 3638,
                "1-100",
                Skill.MINING.mask | Skill.WOODCUTTING.mask | Skill.COOKING.mask,
                Region.KOUREND.value,
            ),
        ],
    )
    conn.commit()


def test_all(conn: sqlite3.Connection) -> None:
    _seed_activities(conn)
    activities = Activity.all(conn)
    assert len(activities) == 4


def test_all_filter_region(conn: sqlite3.Connection) -> None:
    _seed_activities(conn)
    activities = Activity.all(conn, region=Region.KANDARIN)
    assert len(activities) == 2
    names = {a.name for a in activities}
    assert "Barbarian Assault" in names
    assert "Fishing Trawler" in names


def test_all_filter_type(conn: sqlite3.Connection) -> None:
    _seed_activities(conn)
    activities = Activity.all(conn, activity_type=ActivityType.RAID)
    assert len(activities) == 1
    assert activities[0].name == "Chambers of Xeric"


def test_all_filter_region_and_type(conn: sqlite3.Connection) -> None:
    _seed_activities(conn)
    activities = Activity.all(conn, region=Region.KANDARIN, activity_type=ActivityType.MINIGAME)
    assert len(activities) == 2


def test_by_name(conn: sqlite3.Connection) -> None:
    _seed_activities(conn)
    activity = Activity.by_name(conn, "Barbarian Assault")
    assert activity is not None
    assert activity.type == ActivityType.MINIGAME
    assert activity.members is True
    assert activity.players == "5"


def test_by_name_not_found(conn: sqlite3.Connection) -> None:
    _seed_activities(conn)
    assert Activity.by_name(conn, "Nonexistent") is None


def test_search(conn: sqlite3.Connection) -> None:
    _seed_activities(conn)
    results = Activity.search(conn, "Barb")
    assert len(results) == 1
    assert results[0].name == "Barbarian Assault"


def test_by_type(conn: sqlite3.Connection) -> None:
    _seed_activities(conn)
    minigames = Activity.by_type(conn, ActivityType.MINIGAME)
    assert len(minigames) == 2


def test_for_skill(conn: sqlite3.Connection) -> None:
    _seed_activities(conn)
    fishing = Activity.for_skill(conn, Skill.FISHING)
    assert len(fishing) == 1
    assert fishing[0].name == "Fishing Trawler"


def test_for_skill_multiple(conn: sqlite3.Connection) -> None:
    _seed_activities(conn)
    mining = Activity.for_skill(conn, Skill.MINING)
    assert len(mining) == 1
    assert mining[0].name == "Chambers of Xeric"


def test_skill_list(conn: sqlite3.Connection) -> None:
    _seed_activities(conn)
    activity = Activity.by_name(conn, "Barbarian Assault")
    assert activity is not None
    skills = activity.skill_list()
    assert Skill.ATTACK in skills
    assert Skill.STRENGTH in skills
    assert Skill.DEFENCE in skills
    assert Skill.FISHING not in skills


def test_coordinates(conn: sqlite3.Connection) -> None:
    _seed_activities(conn)
    activity = Activity.by_name(conn, "Barbarian Assault")
    assert activity is not None
    assert activity.x == 2533
    assert activity.y == 3571


def test_coordinates_none(conn: sqlite3.Connection) -> None:
    _seed_activities(conn)
    beekeeper = Activity.by_name(conn, "Beekeeper")
    assert beekeeper is not None
    assert beekeeper.x is None
    assert beekeeper.y is None


def test_members_bool(conn: sqlite3.Connection) -> None:
    _seed_activities(conn)
    beekeeper = Activity.by_name(conn, "Beekeeper")
    assert beekeeper is not None
    assert beekeeper.members is False
    assert beekeeper.region is None
