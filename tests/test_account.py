import sqlite3

from ragger.enums import Region, Skill, TaskDifficulty
from ragger.league import Account, LeagueConfig, LeagueTask
from ragger.quest import Quest


def _make_config() -> LeagueConfig:
    return LeagueConfig(
        starting_region=Region.VARLAMORE,
        starting_location="Civitas illa Fortis",
        always_accessible=[Region.VARLAMORE, Region.KARAMJA],
        unlockable_regions=[Region.ASGARNIA, Region.KANDARIN, Region.MORYTANIA],
        max_region_unlocks=3,
        starting_skills={Skill.HERBLORE: 3, Skill.RUNECRAFT: 5},
        autocompleted_quests=["Quest A"],
    )


def _seed(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO quests (name, points) VALUES (?, ?)",
        [("Quest A", 2), ("Quest B", 3), ("Quest C", 1)],
    )
    # A requires B
    b_id = conn.execute("SELECT id FROM quests WHERE name = 'Quest B'").fetchone()[0]
    a_id = conn.execute("SELECT id FROM quests WHERE name = 'Quest A'").fetchone()[0]
    conn.execute("INSERT INTO quest_requirements (required_quest_id, partial) VALUES (?, 0)", (b_id,))
    req_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute("INSERT INTO quest_quest_requirements (quest_id, quest_requirement_id) VALUES (?, ?)", (a_id, req_id))

    conn.executemany(
        "INSERT INTO league_tasks (name, description, difficulty, region) VALUES (?, ?, ?, ?)",
        [
            ("Easy Task", "Do something easy", TaskDifficulty.EASY.value, Region.GENERAL.value),
            ("Hard Task", "Do something hard", TaskDifficulty.HARD.value, Region.KANDARIN.value),
        ],
    )
    conn.commit()


def test_initial_state(conn: sqlite3.Connection) -> None:
    _seed(conn)
    account = Account(_make_config(), conn)

    assert account.get_level(Skill.HERBLORE) == 3
    assert account.get_level(Skill.RUNECRAFT) == 5
    assert account.get_level(Skill.ATTACK) == 1
    assert account.get_level(Skill.HITPOINTS) == 10
    assert Region.VARLAMORE in account.regions
    assert Region.KARAMJA in account.regions


def test_autocompleted_quests(conn: sqlite3.Connection) -> None:
    _seed(conn)
    account = Account(_make_config(), conn)

    # Quest A and its prereq Quest B should be autocompleted
    completed = account.completed_quests()
    names = [q.name for q in completed]
    assert "Quest A" in names
    assert "Quest B" in names
    assert "Quest C" not in names


def test_quest_points(conn: sqlite3.Connection) -> None:
    _seed(conn)
    account = Account(_make_config(), conn)

    # Quest A (2) + Quest B (3)
    assert account.quest_points == 5


def test_complete_quest(conn: sqlite3.Connection) -> None:
    _seed(conn)
    account = Account(_make_config(), conn)

    quest_c = Quest.by_name(conn, "Quest C")
    assert account.complete_quest(quest_c) is True
    assert account.has_quest(quest_c)
    assert account.quest_points == 6  # 5 + 1
    assert account.complete_quest(quest_c) is False  # already completed


def test_complete_quest_fixed_xp(conn: sqlite3.Connection) -> None:
    _seed(conn)
    account = Account(_make_config(), conn)

    quest_c = Quest.by_name(conn, "Quest C")
    # Add a fixed XP reward to Quest C
    conn.execute(
        "INSERT INTO experience_rewards (eligible_skills, amount) VALUES (?, ?)",
        (Skill.COOKING.mask, 300),
    )
    reward_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO quest_experience_rewards (quest_id, experience_reward_id) VALUES (?, ?)",
        (quest_c.id, reward_id),
    )
    conn.commit()

    account.complete_quest(quest_c)
    assert account.get_xp(Skill.COOKING) == 300


def test_complete_quest_choice_xp(conn: sqlite3.Connection) -> None:
    _seed(conn)
    account = Account(_make_config(), conn)

    quest_c = Quest.by_name(conn, "Quest C")
    # Add a choice XP reward (Attack or Strength)
    mask = Skill.ATTACK.mask | Skill.STRENGTH.mask
    conn.execute(
        "INSERT INTO experience_rewards (eligible_skills, amount) VALUES (?, ?)",
        (mask, 5000),
    )
    reward_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO quest_experience_rewards (quest_id, experience_reward_id) VALUES (?, ?)",
        (quest_c.id, reward_id),
    )
    conn.commit()

    account.complete_quest(quest_c, xp_choices={reward_id: Skill.STRENGTH})
    assert account.get_xp(Skill.STRENGTH) == 5000
    assert account.get_xp(Skill.ATTACK) == 0


def test_complete_quest_choice_xp_missing_raises(conn: sqlite3.Connection) -> None:
    _seed(conn)
    account = Account(_make_config(), conn)

    quest_c = Quest.by_name(conn, "Quest C")
    mask = Skill.ATTACK.mask | Skill.STRENGTH.mask
    conn.execute(
        "INSERT INTO experience_rewards (eligible_skills, amount) VALUES (?, ?)",
        (mask, 5000),
    )
    reward_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO quest_experience_rewards (quest_id, experience_reward_id) VALUES (?, ?)",
        (quest_c.id, reward_id),
    )
    conn.commit()

    import pytest
    with pytest.raises(ValueError, match="requires a skill choice"):
        account.complete_quest(quest_c)


def test_complete_quest_choice_xp_invalid_skill_raises(conn: sqlite3.Connection) -> None:
    _seed(conn)
    account = Account(_make_config(), conn)

    quest_c = Quest.by_name(conn, "Quest C")
    mask = Skill.ATTACK.mask | Skill.STRENGTH.mask
    conn.execute(
        "INSERT INTO experience_rewards (eligible_skills, amount) VALUES (?, ?)",
        (mask, 5000),
    )
    reward_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO quest_experience_rewards (quest_id, experience_reward_id) VALUES (?, ?)",
        (quest_c.id, reward_id),
    )
    conn.commit()

    import pytest
    with pytest.raises(ValueError, match="not eligible"):
        account.complete_quest(quest_c, xp_choices={reward_id: Skill.COOKING})


def test_complete_task(conn: sqlite3.Connection) -> None:
    _seed(conn)
    account = Account(_make_config(), conn)

    assert account.league_points == 0
    easy = LeagueTask.by_name(conn, "Easy Task")
    assert account.complete_task(easy) is True
    assert account.league_points == 10
    assert account.complete_task(easy) is False  # already completed

    hard = LeagueTask.by_name(conn, "Hard Task")
    assert account.complete_task(hard) is True
    assert account.league_points == 90  # 10 + 80


def test_unlock_region(conn: sqlite3.Connection) -> None:
    _seed(conn)
    account = Account(_make_config(), conn)

    assert not account.has_region(Region.KANDARIN)
    assert account.unlock_region(Region.KANDARIN) is True
    assert account.has_region(Region.KANDARIN)
    assert account.unlock_region(Region.KANDARIN) is False  # already unlocked


def test_unlock_region_limit(conn: sqlite3.Connection) -> None:
    _seed(conn)
    account = Account(_make_config(), conn)

    account.unlock_region(Region.ASGARNIA)
    account.unlock_region(Region.KANDARIN)
    account.unlock_region(Region.MORYTANIA)
    assert len(account.unlocked_regions) == 5  # 2 always + 3 unlocked

    # Can't unlock more — not in unlockable list
    assert account.unlock_region(Region.WILDERNESS) is False
    assert not account.has_region(Region.WILDERNESS)


def test_set_skill(conn: sqlite3.Connection) -> None:
    _seed(conn)
    account = Account(_make_config(), conn)

    account.set_skill(Skill.MINING, 60)
    assert account.has_skill(Skill.MINING, 60)
    assert account.has_skill(Skill.MINING, 50)
    assert not account.has_skill(Skill.MINING, 61)


def test_add_xp(conn: sqlite3.Connection) -> None:
    _seed(conn)
    account = Account(_make_config(), conn)

    assert account.get_level(Skill.ATTACK) == 1
    account.add_xp(Skill.ATTACK, 83)
    assert account.get_level(Skill.ATTACK) == 2
    assert account.get_xp(Skill.ATTACK) == 83
    account.add_xp(Skill.ATTACK, 91)  # 83 + 91 = 174
    assert account.get_level(Skill.ATTACK) == 3


def test_general_region_always_accessible(conn: sqlite3.Connection) -> None:
    _seed(conn)
    account = Account(_make_config(), conn)

    assert account.has_region(Region.GENERAL)
