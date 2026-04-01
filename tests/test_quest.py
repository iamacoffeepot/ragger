import sqlite3

from clogger.enums import Skill
from clogger.quest import Quest
from clogger.requirements.quest import QuestRequirement
from clogger.requirements.quest_point import QuestPointRequirement
from clogger.requirements.skill import SkillRequirement
from clogger.rewards.experience import ExperienceReward
from clogger.rewards.item import ItemReward


def _seed_quests(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO quests (name, points) VALUES (?, ?)",
        [("Cook's Assistant", 1), ("Dragon Slayer I", 2), ("Lost City", 3)],
    )
    conn.commit()


def test_all(conn: sqlite3.Connection) -> None:
    _seed_quests(conn)
    quests = Quest.all(conn)
    assert len(quests) == 3
    assert all(isinstance(q, Quest) for q in quests)
    assert quests[0].name == "Cook's Assistant"


def test_by_name(conn: sqlite3.Connection) -> None:
    _seed_quests(conn)
    quest = Quest.by_name(conn, "Dragon Slayer I")
    assert quest is not None
    assert quest.name == "Dragon Slayer I"
    assert quest.points == 2


def test_by_name_not_found(conn: sqlite3.Connection) -> None:
    _seed_quests(conn)
    assert Quest.by_name(conn, "Nonexistent Quest") is None


def test_xp_rewards(conn: sqlite3.Connection) -> None:
    _seed_quests(conn)
    quest = Quest.by_name(conn, "Cook's Assistant")
    conn.execute(
        "INSERT INTO experience_rewards (eligible_skills, amount) VALUES (?, ?)",
        (Skill.COOKING.mask, 300),
    )
    reward_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO quest_experience_rewards (quest_id, experience_reward_id) VALUES (?, ?)",
        (quest.id, reward_id),
    )
    conn.commit()

    rewards = quest.xp_rewards(conn)
    assert len(rewards) == 1
    assert isinstance(rewards[0], ExperienceReward)
    assert rewards[0].amount == 300
    assert rewards[0].eligible_skills == Skill.COOKING.mask


def test_item_rewards(conn: sqlite3.Connection) -> None:
    _seed_quests(conn)
    quest = Quest.by_name(conn, "Cook's Assistant")
    conn.execute("INSERT INTO items (name) VALUES (?)", ("Coins",))
    item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO item_rewards (item_id, quantity) VALUES (?, ?)",
        (item_id, 500),
    )
    reward_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO quest_item_rewards (quest_id, item_reward_id) VALUES (?, ?)",
        (quest.id, reward_id),
    )
    conn.commit()

    rewards = quest.item_rewards(conn)
    assert len(rewards) == 1
    assert isinstance(rewards[0], ItemReward)
    assert rewards[0].quantity == 500


def test_skill_requirements(conn: sqlite3.Connection) -> None:
    _seed_quests(conn)
    quest = Quest.by_name(conn, "Dragon Slayer I")
    conn.execute(
        "INSERT INTO skill_requirements (skill, level) VALUES (?, ?)",
        (Skill.MINING.value, 40),
    )
    req_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO quest_skill_requirements (quest_id, skill_requirement_id) VALUES (?, ?)",
        (quest.id, req_id),
    )
    conn.commit()

    reqs = quest.skill_requirements(conn)
    assert len(reqs) == 1
    assert isinstance(reqs[0], SkillRequirement)
    assert reqs[0].skill == Skill.MINING
    assert reqs[0].level == 40


def test_quest_requirements(conn: sqlite3.Connection) -> None:
    _seed_quests(conn)
    ds1 = Quest.by_name(conn, "Dragon Slayer I")
    lc = Quest.by_name(conn, "Lost City")
    conn.execute(
        "INSERT INTO quest_requirements (required_quest_id, partial) VALUES (?, ?)",
        (lc.id, 0),
    )
    req_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO quest_quest_requirements (quest_id, quest_requirement_id) VALUES (?, ?)",
        (ds1.id, req_id),
    )
    conn.commit()

    reqs = ds1.quest_requirements(conn)
    assert len(reqs) == 1
    assert isinstance(reqs[0], QuestRequirement)
    assert reqs[0].required_quest_id == lc.id
    assert reqs[0].partial is False


def test_quest_point_requirement(conn: sqlite3.Connection) -> None:
    _seed_quests(conn)
    quest = Quest.by_name(conn, "Dragon Slayer I")
    conn.execute("INSERT INTO quest_point_requirements (points) VALUES (?)", (32,))
    req_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO quest_quest_point_requirements (quest_id, quest_point_requirement_id) VALUES (?, ?)",
        (quest.id, req_id),
    )
    conn.commit()

    req = quest.quest_point_requirement(conn)
    assert req is not None
    assert isinstance(req, QuestPointRequirement)
    assert req.points == 32


def test_quest_point_requirement_none(conn: sqlite3.Connection) -> None:
    _seed_quests(conn)
    quest = Quest.by_name(conn, "Cook's Assistant")
    assert quest.quest_point_requirement(conn) is None


def test_requirement_chain(conn: sqlite3.Connection) -> None:
    # A -> B -> C (A requires B, B requires C)
    conn.executemany(
        "INSERT INTO quests (name, points) VALUES (?, ?)",
        [("Quest A", 1), ("Quest B", 1), ("Quest C", 1)],
    )
    a = Quest.by_name(conn, "Quest A")
    b = Quest.by_name(conn, "Quest B")
    c = Quest.by_name(conn, "Quest C")

    # A requires B
    conn.execute(
        "INSERT INTO quest_requirements (required_quest_id, partial) VALUES (?, ?)",
        (b.id, 0),
    )
    req_b_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO quest_quest_requirements (quest_id, quest_requirement_id) VALUES (?, ?)",
        (a.id, req_b_id),
    )

    # B requires C
    conn.execute(
        "INSERT INTO quest_requirements (required_quest_id, partial) VALUES (?, ?)",
        (c.id, 0),
    )
    req_c_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO quest_quest_requirements (quest_id, quest_requirement_id) VALUES (?, ?)",
        (b.id, req_c_id),
    )
    conn.commit()

    chain = a.requirement_chain(conn)
    names = [q.name for q in chain]
    # C should come before B (depth-first, post-order)
    assert "Quest C" in names
    assert "Quest B" in names
    assert names.index("Quest C") < names.index("Quest B")
