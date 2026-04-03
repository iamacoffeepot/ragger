import sqlite3

from ragger.diary import DiaryTask
from ragger.enums import DiaryLocation, DiaryTier


def _seed_diary_tasks(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO diary_tasks (location, tier, description) VALUES (?, ?, ?)",
        [
            ("Ardougne", "Easy", "Steal a cake"),
            ("Ardougne", "Medium", "Grapple over Yanille wall"),
            ("Ardougne", "Hard", "Steal from a chest"),
            ("Karamja", "Easy", "Pick 5 bananas"),
            ("Karamja", "Easy", "Use the rope swing"),
        ],
    )
    conn.commit()


def test_all(conn: sqlite3.Connection) -> None:
    _seed_diary_tasks(conn)
    tasks = DiaryTask.all(conn)
    assert len(tasks) == 5
    assert all(isinstance(t, DiaryTask) for t in tasks)


def test_filter_by_location(conn: sqlite3.Connection) -> None:
    _seed_diary_tasks(conn)
    tasks = DiaryTask.all(conn, location=DiaryLocation.ARDOUGNE)
    assert len(tasks) == 3
    assert all(t.location == DiaryLocation.ARDOUGNE for t in tasks)


def test_filter_by_tier(conn: sqlite3.Connection) -> None:
    _seed_diary_tasks(conn)
    tasks = DiaryTask.all(conn, tier=DiaryTier.EASY)
    assert len(tasks) == 3
    assert all(t.tier == DiaryTier.EASY for t in tasks)


def test_filter_by_location_and_tier(conn: sqlite3.Connection) -> None:
    _seed_diary_tasks(conn)
    tasks = DiaryTask.all(conn, location=DiaryLocation.KARAMJA, tier=DiaryTier.EASY)
    assert len(tasks) == 2
    assert all(t.location == DiaryLocation.KARAMJA and t.tier == DiaryTier.EASY for t in tasks)


def test_filter_no_results(conn: sqlite3.Connection) -> None:
    _seed_diary_tasks(conn)
    tasks = DiaryTask.all(conn, location=DiaryLocation.WILDERNESS)
    assert len(tasks) == 0
