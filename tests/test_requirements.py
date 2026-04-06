import sqlite3

from ragger.enums import DiaryLocation, DiaryTier, Region, Skill
from ragger.requirements import (
    GroupDiaryRequirement,
    GroupItemRequirement,
    GroupQuestPointRequirement,
    GroupQuestRequirement,
    GroupRegionRequirement,
    GroupSkillRequirement,
    RequirementGroup,
)
from ragger.wiki import (
    add_group_requirement,
    create_requirement_group,
    link_group_requirement,
    link_requirement_group,
)


def _seed(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO quests (name, points) VALUES ('Dragon Slayer I', 2)")
    conn.execute("INSERT INTO quests (name, points) VALUES ('Lost City', 3)")
    conn.execute("INSERT INTO items (name) VALUES ('Coins')")
    conn.execute("INSERT INTO items (name) VALUES ('Anti-dragon shield')")
    conn.commit()


def test_single_skill_requirement(conn: sqlite3.Connection) -> None:
    """One group with one skill requirement — simplest AND case."""
    _seed(conn)
    conn.execute("INSERT INTO quests (name, points) VALUES ('Test Quest', 1)")
    quest_id = conn.execute("SELECT id FROM quests WHERE name = 'Test Quest'").fetchone()[0]

    link_group_requirement(
        conn,
        "group_skill_requirements",
        {"skill": Skill.MINING.value, "level": 60},
        "quest_requirement_groups",
        "quest_id",
        quest_id,
    )
    conn.commit()

    groups = RequirementGroup.for_quest(conn, quest_id)
    assert len(groups) == 1
    reqs = groups[0].skill_requirements(conn)
    assert len(reqs) == 1
    assert isinstance(reqs[0], GroupSkillRequirement)
    assert reqs[0].skill == Skill.MINING
    assert reqs[0].level == 60
    assert reqs[0].boostable is False


def test_multiple_and_groups(conn: sqlite3.Connection) -> None:
    """Two groups = AND. Must satisfy both."""
    _seed(conn)
    conn.execute("INSERT INTO quests (name, points) VALUES ('Test Quest', 1)")
    quest_id = conn.execute("SELECT id FROM quests WHERE name = 'Test Quest'").fetchone()[0]

    link_group_requirement(
        conn,
        "group_skill_requirements",
        {"skill": Skill.MINING.value, "level": 60},
        "quest_requirement_groups",
        "quest_id",
        quest_id,
    )
    link_group_requirement(
        conn,
        "group_skill_requirements",
        {"skill": Skill.SMITHING.value, "level": 50},
        "quest_requirement_groups",
        "quest_id",
        quest_id,
    )
    conn.commit()

    groups = RequirementGroup.for_quest(conn, quest_id)
    assert len(groups) == 2
    skills = []
    for g in groups:
        skills.extend(g.skill_requirements(conn))
    assert len(skills) == 2
    assert {r.skill for r in skills} == {Skill.MINING, Skill.SMITHING}


def test_or_group(conn: sqlite3.Connection) -> None:
    """One group with two item requirements = OR. Either item satisfies."""
    _seed(conn)
    conn.execute("INSERT INTO league_tasks (name, description, difficulty, region) VALUES ('Test Task', 'desc', 1, 1)")
    task_id = conn.execute("SELECT id FROM league_tasks WHERE name = 'Test Task'").fetchone()[0]
    coins_id = conn.execute("SELECT id FROM items WHERE name = 'Coins'").fetchone()[0]
    shield_id = conn.execute("SELECT id FROM items WHERE name = 'Anti-dragon shield'").fetchone()[0]

    group_id = create_requirement_group(conn)
    add_group_requirement(conn, group_id, "group_item_requirements", {"item_id": coins_id, "quantity": 10})
    add_group_requirement(conn, group_id, "group_item_requirements", {"item_id": shield_id, "quantity": 1})
    link_requirement_group(conn, "league_task_requirement_groups", "league_task_id", task_id, group_id)
    conn.commit()

    groups = RequirementGroup.for_league_task(conn, task_id)
    assert len(groups) == 1
    items = groups[0].item_requirements(conn)
    assert len(items) == 2
    assert {r.item_id for r in items} == {coins_id, shield_id}


def test_mixed_types_in_group(conn: sqlite3.Connection) -> None:
    """A group can contain different requirement types (all OR'd)."""
    _seed(conn)
    conn.execute("INSERT INTO league_tasks (name, description, difficulty, region) VALUES ('Mixed', 'desc', 1, 1)")
    task_id = conn.execute("SELECT id FROM league_tasks WHERE name = 'Mixed'").fetchone()[0]
    ds_id = conn.execute("SELECT id FROM quests WHERE name = 'Dragon Slayer I'").fetchone()[0]

    group_id = create_requirement_group(conn)
    add_group_requirement(conn, group_id, "group_skill_requirements", {"skill": Skill.ATTACK.value, "level": 40})
    add_group_requirement(conn, group_id, "group_quest_requirements", {"required_quest_id": ds_id})
    link_requirement_group(conn, "league_task_requirement_groups", "league_task_id", task_id, group_id)
    conn.commit()

    groups = RequirementGroup.for_league_task(conn, task_id)
    assert len(groups) == 1
    g = groups[0]
    assert len(g.skill_requirements(conn)) == 1
    assert len(g.quest_requirements(conn)) == 1
    assert g.skill_requirements(conn)[0].skill == Skill.ATTACK
    assert g.quest_requirements(conn)[0].required_quest_id == ds_id


def test_quest_requirement_with_partial(conn: sqlite3.Connection) -> None:
    _seed(conn)
    conn.execute("INSERT INTO diary_tasks (location, tier, description) VALUES ('Lumbridge & Draynor', 'Easy', 'test')")
    task_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    ds_id = conn.execute("SELECT id FROM quests WHERE name = 'Dragon Slayer I'").fetchone()[0]

    link_group_requirement(
        conn,
        "group_quest_requirements",
        {"required_quest_id": ds_id, "partial": 1},
        "diary_task_requirement_groups",
        "diary_task_id",
        task_id,
    )
    conn.commit()

    groups = RequirementGroup.for_diary_task(conn, task_id)
    assert len(groups) == 1
    reqs = groups[0].quest_requirements(conn)
    assert len(reqs) == 1
    assert reqs[0].partial is True


def test_quest_point_requirement(conn: sqlite3.Connection) -> None:
    _seed(conn)
    conn.execute("INSERT INTO quests (name, points) VALUES ('QP Quest', 1)")
    quest_id = conn.execute("SELECT id FROM quests WHERE name = 'QP Quest'").fetchone()[0]

    link_group_requirement(
        conn,
        "group_quest_point_requirements",
        {"points": 32},
        "quest_requirement_groups",
        "quest_id",
        quest_id,
    )
    conn.commit()

    groups = RequirementGroup.for_quest(conn, quest_id)
    qp_reqs = groups[0].quest_point_requirements(conn)
    assert len(qp_reqs) == 1
    assert isinstance(qp_reqs[0], GroupQuestPointRequirement)
    assert qp_reqs[0].points == 32


def test_diary_requirement(conn: sqlite3.Connection) -> None:
    _seed(conn)
    conn.execute("INSERT INTO league_tasks (name, description, difficulty, region) VALUES ('Diary Task', 'desc', 1, 1)")
    task_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    link_group_requirement(
        conn,
        "group_diary_requirements",
        {"location": DiaryLocation.VARROCK.value, "tier": DiaryTier.HARD.value},
        "league_task_requirement_groups",
        "league_task_id",
        task_id,
    )
    conn.commit()

    groups = RequirementGroup.for_league_task(conn, task_id)
    reqs = groups[0].diary_requirements(conn)
    assert len(reqs) == 1
    assert isinstance(reqs[0], GroupDiaryRequirement)
    assert reqs[0].location == DiaryLocation.VARROCK
    assert reqs[0].tier == DiaryTier.HARD


def test_region_requirement(conn: sqlite3.Connection) -> None:
    _seed(conn)
    conn.execute("INSERT INTO league_tasks (name, description, difficulty, region) VALUES ('Region Task', 'desc', 1, 1)")
    task_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    link_group_requirement(
        conn,
        "group_region_requirements",
        {"region": Region.MISTHALIN.value},
        "league_task_requirement_groups",
        "league_task_id",
        task_id,
    )
    conn.commit()

    groups = RequirementGroup.for_league_task(conn, task_id)
    reqs = groups[0].region_requirements(conn)
    assert len(reqs) == 1
    assert isinstance(reqs[0], GroupRegionRequirement)
    assert reqs[0].region == Region.MISTHALIN


def test_boostable_skill(conn: sqlite3.Connection) -> None:
    _seed(conn)
    conn.execute("INSERT INTO quests (name, points) VALUES ('Boost Quest', 1)")
    quest_id = conn.execute("SELECT id FROM quests WHERE name = 'Boost Quest'").fetchone()[0]

    link_group_requirement(
        conn,
        "group_skill_requirements",
        {"skill": Skill.HERBLORE.value, "level": 45, "boostable": 1},
        "quest_requirement_groups",
        "quest_id",
        quest_id,
    )
    conn.commit()

    groups = RequirementGroup.for_quest(conn, quest_id)
    req = groups[0].skill_requirements(conn)[0]
    assert req.boostable is True
    assert req.level == 45


def test_empty_groups(conn: sqlite3.Connection) -> None:
    _seed(conn)
    conn.execute("INSERT INTO quests (name, points) VALUES ('No Reqs', 0)")
    quest_id = conn.execute("SELECT id FROM quests WHERE name = 'No Reqs'").fetchone()[0]
    conn.commit()

    groups = RequirementGroup.for_quest(conn, quest_id)
    assert groups == []


def test_complex_and_or(conn: sqlite3.Connection) -> None:
    """AND of: (Mining 60) AND (Coins OR Shield) — two groups."""
    _seed(conn)
    conn.execute("INSERT INTO league_tasks (name, description, difficulty, region) VALUES ('Complex', 'desc', 1, 1)")
    task_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    coins_id = conn.execute("SELECT id FROM items WHERE name = 'Coins'").fetchone()[0]
    shield_id = conn.execute("SELECT id FROM items WHERE name = 'Anti-dragon shield'").fetchone()[0]

    # Group 1: Mining 60 (AND)
    link_group_requirement(
        conn,
        "group_skill_requirements",
        {"skill": Skill.MINING.value, "level": 60},
        "league_task_requirement_groups",
        "league_task_id",
        task_id,
    )

    # Group 2: Coins OR Shield (OR)
    group_id = create_requirement_group(conn)
    add_group_requirement(conn, group_id, "group_item_requirements", {"item_id": coins_id, "quantity": 10})
    add_group_requirement(conn, group_id, "group_item_requirements", {"item_id": shield_id, "quantity": 1})
    link_requirement_group(conn, "league_task_requirement_groups", "league_task_id", task_id, group_id)
    conn.commit()

    groups = RequirementGroup.for_league_task(conn, task_id)
    assert len(groups) == 2

    # One group has a skill, the other has items
    skill_groups = [g for g in groups if g.skill_requirements(conn)]
    item_groups = [g for g in groups if g.item_requirements(conn)]
    assert len(skill_groups) == 1
    assert len(item_groups) == 1
    assert len(item_groups[0].item_requirements(conn)) == 2
