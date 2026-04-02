import sqlite3

from clogger.enums import DiaryLocation, DiaryTier, Region, Skill, TaskDifficulty
from clogger.league import LeagueTask
from clogger.requirements import DiaryRequirement, ItemRequirement, QuestRequirement, SkillRequirement


def _seed_tasks(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO league_tasks (name, description, difficulty, region) VALUES (?, ?, ?, ?)",
        [
            ("Kill a Goblin", "Kill a goblin", TaskDifficulty.EASY.value, Region.MISTHALIN.value),
            ("50 Wintertodt Kills", "Kill Wintertodt 50 times", TaskDifficulty.HARD.value, Region.KOUREND.value),
            ("Achieve Level 99", "Get 99 in any skill", TaskDifficulty.ELITE.value, Region.GENERAL.value),
        ],
    )
    conn.commit()


def test_all(conn: sqlite3.Connection) -> None:
    _seed_tasks(conn)
    tasks = LeagueTask.all(conn)
    assert len(tasks) == 3
    assert all(isinstance(t, LeagueTask) for t in tasks)


def test_all_filter_difficulty(conn: sqlite3.Connection) -> None:
    _seed_tasks(conn)
    tasks = LeagueTask.all(conn, difficulty=TaskDifficulty.HARD)
    assert len(tasks) == 1
    assert tasks[0].name == "50 Wintertodt Kills"


def test_all_filter_region(conn: sqlite3.Connection) -> None:
    _seed_tasks(conn)
    tasks = LeagueTask.all(conn, region=Region.KOUREND)
    assert len(tasks) == 1
    assert tasks[0].region == Region.KOUREND


def test_by_name(conn: sqlite3.Connection) -> None:
    _seed_tasks(conn)
    task = LeagueTask.by_name(conn, "Kill a Goblin")
    assert task is not None
    assert task.difficulty == TaskDifficulty.EASY
    assert task.region == Region.MISTHALIN
    assert task.points == 10


def test_by_name_not_found(conn: sqlite3.Connection) -> None:
    _seed_tasks(conn)
    assert LeagueTask.by_name(conn, "Nonexistent") is None


def test_points(conn: sqlite3.Connection) -> None:
    _seed_tasks(conn)
    tasks = LeagueTask.all(conn)
    points = {t.name: t.points for t in tasks}
    assert points["Kill a Goblin"] == 10
    assert points["50 Wintertodt Kills"] == 80
    assert points["Achieve Level 99"] == 200


def test_general_region(conn: sqlite3.Connection) -> None:
    _seed_tasks(conn)
    task = LeagueTask.by_name(conn, "Achieve Level 99")
    assert task.region == Region.GENERAL


def test_by_skill(conn: sqlite3.Connection) -> None:
    _seed_tasks(conn)
    task = LeagueTask.by_name(conn, "50 Wintertodt Kills")
    conn.execute(
        "INSERT INTO skill_requirements (skill, level) VALUES (?, ?)",
        (Skill.FIREMAKING.value, 50),
    )
    req_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO league_task_skill_requirements (league_task_id, skill_requirement_id) VALUES (?, ?)",
        (task.id, req_id),
    )
    conn.commit()

    tasks = LeagueTask.by_skill(conn, Skill.FIREMAKING)
    assert len(tasks) == 1
    assert tasks[0].name == "50 Wintertodt Kills"


def test_by_skill_with_filters(conn: sqlite3.Connection) -> None:
    _seed_tasks(conn)
    conn.execute(
        "INSERT INTO skill_requirements (skill, level) VALUES (?, ?)",
        (Skill.ATTACK.value, 10),
    )
    req_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    for task_name in ("Kill a Goblin", "50 Wintertodt Kills"):
        task = LeagueTask.by_name(conn, task_name)
        conn.execute(
            "INSERT INTO league_task_skill_requirements (league_task_id, skill_requirement_id) VALUES (?, ?)",
            (task.id, req_id),
        )
    conn.commit()

    # Filter by region
    tasks = LeagueTask.by_skill(conn, Skill.ATTACK, region=Region.KOUREND)
    assert len(tasks) == 1
    assert tasks[0].name == "50 Wintertodt Kills"

    # Filter by difficulty
    tasks = LeagueTask.by_skill(conn, Skill.ATTACK, difficulty=TaskDifficulty.EASY)
    assert len(tasks) == 1
    assert tasks[0].name == "Kill a Goblin"


def test_skill_requirements(conn: sqlite3.Connection) -> None:
    _seed_tasks(conn)
    task = LeagueTask.by_name(conn, "50 Wintertodt Kills")
    conn.execute(
        "INSERT INTO skill_requirements (skill, level) VALUES (?, ?)",
        (Skill.FIREMAKING.value, 50),
    )
    req_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO league_task_skill_requirements (league_task_id, skill_requirement_id) VALUES (?, ?)",
        (task.id, req_id),
    )
    conn.commit()

    reqs = task.skill_requirements(conn)
    assert len(reqs) == 1
    assert isinstance(reqs[0], SkillRequirement)
    assert reqs[0].skill == Skill.FIREMAKING
    assert reqs[0].level == 50


def test_quest_requirements(conn: sqlite3.Connection) -> None:
    _seed_tasks(conn)
    task = LeagueTask.by_name(conn, "Kill a Goblin")
    conn.execute("INSERT INTO quests (name, points) VALUES (?, ?)", ("Goblin Diplomacy", 5))
    quest_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO quest_requirements (required_quest_id, partial) VALUES (?, ?)",
        (quest_id, 0),
    )
    req_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO league_task_quest_requirements (league_task_id, quest_requirement_id) VALUES (?, ?)",
        (task.id, req_id),
    )
    conn.commit()

    reqs = task.quest_requirements(conn)
    assert len(reqs) == 1
    assert isinstance(reqs[0], QuestRequirement)
    assert reqs[0].required_quest_id == quest_id


def test_item_requirements(conn: sqlite3.Connection) -> None:
    _seed_tasks(conn)
    task = LeagueTask.by_name(conn, "Kill a Goblin")
    conn.execute("INSERT INTO items (name) VALUES (?)", ("Bronze sword",))
    item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO item_requirements (item_id, quantity) VALUES (?, ?)",
        (item_id, 1),
    )
    req_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO league_task_item_requirements (league_task_id, item_requirement_id) VALUES (?, ?)",
        (task.id, req_id),
    )
    conn.commit()

    reqs = task.item_requirements(conn)
    assert len(reqs) == 1
    assert isinstance(reqs[0], ItemRequirement)
    assert reqs[0].item_id == item_id


def test_diary_requirements(conn: sqlite3.Connection) -> None:
    _seed_tasks(conn)
    task = LeagueTask.by_name(conn, "50 Wintertodt Kills")
    conn.execute(
        "INSERT INTO diary_requirements (location, tier) VALUES (?, ?)",
        (DiaryLocation.KOUREND_KEBOS.value, DiaryTier.EASY.value),
    )
    req_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO league_task_diary_requirements (league_task_id, diary_requirement_id) VALUES (?, ?)",
        (task.id, req_id),
    )
    conn.commit()

    reqs = task.diary_requirements(conn)
    assert len(reqs) == 1
    assert isinstance(reqs[0], DiaryRequirement)
    assert reqs[0].location == DiaryLocation.KOUREND_KEBOS
    assert reqs[0].tier == DiaryTier.EASY
