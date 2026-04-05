import sqlite3
from pathlib import Path

from ragger.enums import ALL_REGIONS_MASK, ALL_SKILLS_MASK, DiaryLocation, DiaryTier, Region, ShopType, Skill, TaskDifficulty

_skill_ids = ", ".join(str(s.value) for s in Skill)
_region_ids = ", ".join(str(r.value) for r in Region)
_difficulty_ids = ", ".join(str(d.value) for d in TaskDifficulty)
_diary_location_values = ", ".join(f"'{l.value}'" for l in DiaryLocation)
_diary_tier_values = ", ".join(f"'{t.value}'" for t in DiaryTier)

SCHEMAS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS quests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        points INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS skill_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        skill INTEGER NOT NULL CHECK(skill IN ({_skill_ids})),
        level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 99),
        UNIQUE(skill, level)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quest_point_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        points INTEGER NOT NULL UNIQUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS item_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (item_id) REFERENCES items(id),
        UNIQUE(item_id, quantity)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS diary_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location TEXT NOT NULL CHECK(location IN ({_diary_location_values})),
        tier TEXT NOT NULL CHECK(tier IN ({_diary_tier_values})),
        description TEXT NOT NULL
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS diary_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location TEXT NOT NULL CHECK(location IN ({_diary_location_values})),
        tier TEXT NOT NULL CHECK(tier IN ({_diary_tier_values})),
        UNIQUE(location, tier)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS league_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        difficulty INTEGER NOT NULL CHECK(difficulty IN ({_difficulty_ids})),
        region INTEGER NOT NULL CHECK(region IN ({_region_ids}))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS league_task_skill_requirements (
        league_task_id INTEGER NOT NULL,
        skill_requirement_id INTEGER NOT NULL,
        PRIMARY KEY (league_task_id, skill_requirement_id),
        FOREIGN KEY (league_task_id) REFERENCES league_tasks(id),
        FOREIGN KEY (skill_requirement_id) REFERENCES skill_requirements(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS league_task_quest_requirements (
        league_task_id INTEGER NOT NULL,
        quest_requirement_id INTEGER NOT NULL,
        PRIMARY KEY (league_task_id, quest_requirement_id),
        FOREIGN KEY (league_task_id) REFERENCES league_tasks(id),
        FOREIGN KEY (quest_requirement_id) REFERENCES quest_requirements(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS league_task_item_requirements (
        league_task_id INTEGER NOT NULL,
        item_requirement_id INTEGER NOT NULL,
        PRIMARY KEY (league_task_id, item_requirement_id),
        FOREIGN KEY (league_task_id) REFERENCES league_tasks(id),
        FOREIGN KEY (item_requirement_id) REFERENCES item_requirements(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS league_task_diary_requirements (
        league_task_id INTEGER NOT NULL,
        diary_requirement_id INTEGER NOT NULL,
        PRIMARY KEY (league_task_id, diary_requirement_id),
        FOREIGN KEY (league_task_id) REFERENCES league_tasks(id),
        FOREIGN KEY (diary_requirement_id) REFERENCES diary_requirements(id)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS region_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        regions INTEGER NOT NULL CHECK(regions > 0 AND regions <= {ALL_REGIONS_MASK}),
        any_region INTEGER NOT NULL DEFAULT 0,
        UNIQUE(regions, any_region)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS league_task_region_requirements (
        league_task_id INTEGER NOT NULL,
        region_requirement_id INTEGER NOT NULL,
        PRIMARY KEY (league_task_id, region_requirement_id),
        FOREIGN KEY (league_task_id) REFERENCES league_tasks(id),
        FOREIGN KEY (region_requirement_id) REFERENCES region_requirements(id)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS experience_rewards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        eligible_skills INTEGER NOT NULL CHECK(eligible_skills > 0 AND eligible_skills <= {ALL_SKILLS_MASK}),
        amount INTEGER NOT NULL CHECK(amount > 0),
        UNIQUE(eligible_skills, amount)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS item_rewards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (item_id) REFERENCES items(id),
        UNIQUE(item_id, quantity)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quest_experience_rewards (
        quest_id INTEGER NOT NULL,
        experience_reward_id INTEGER NOT NULL,
        PRIMARY KEY (quest_id, experience_reward_id),
        FOREIGN KEY (quest_id) REFERENCES quests(id),
        FOREIGN KEY (experience_reward_id) REFERENCES experience_rewards(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quest_item_rewards (
        quest_id INTEGER NOT NULL,
        item_reward_id INTEGER NOT NULL,
        PRIMARY KEY (quest_id, item_reward_id),
        FOREIGN KEY (quest_id) REFERENCES quests(id),
        FOREIGN KEY (item_reward_id) REFERENCES item_rewards(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quest_region_requirements (
        quest_id INTEGER NOT NULL,
        region_requirement_id INTEGER NOT NULL,
        PRIMARY KEY (quest_id, region_requirement_id),
        FOREIGN KEY (quest_id) REFERENCES quests(id),
        FOREIGN KEY (region_requirement_id) REFERENCES region_requirements(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quest_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        required_quest_id INTEGER NOT NULL,
        partial INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (required_quest_id) REFERENCES quests(id),
        UNIQUE(required_quest_id, partial)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quest_quest_point_requirements (
        quest_id INTEGER NOT NULL,
        quest_point_requirement_id INTEGER NOT NULL,
        PRIMARY KEY (quest_id, quest_point_requirement_id),
        FOREIGN KEY (quest_id) REFERENCES quests(id),
        FOREIGN KEY (quest_point_requirement_id) REFERENCES quest_point_requirements(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quest_skill_requirements (
        quest_id INTEGER NOT NULL,
        skill_requirement_id INTEGER NOT NULL,
        PRIMARY KEY (quest_id, skill_requirement_id),
        FOREIGN KEY (quest_id) REFERENCES quests(id),
        FOREIGN KEY (skill_requirement_id) REFERENCES skill_requirements(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS diary_task_skill_requirements (
        diary_task_id INTEGER NOT NULL,
        skill_requirement_id INTEGER NOT NULL,
        PRIMARY KEY (diary_task_id, skill_requirement_id),
        FOREIGN KEY (diary_task_id) REFERENCES diary_tasks(id),
        FOREIGN KEY (skill_requirement_id) REFERENCES skill_requirements(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS diary_task_quest_requirements (
        diary_task_id INTEGER NOT NULL,
        quest_requirement_id INTEGER NOT NULL,
        PRIMARY KEY (diary_task_id, quest_requirement_id),
        FOREIGN KEY (diary_task_id) REFERENCES diary_tasks(id),
        FOREIGN KEY (quest_requirement_id) REFERENCES quest_requirements(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS diary_task_item_requirements (
        diary_task_id INTEGER NOT NULL,
        item_requirement_id INTEGER NOT NULL,
        PRIMARY KEY (diary_task_id, item_requirement_id),
        FOREIGN KEY (diary_task_id) REFERENCES diary_tasks(id),
        FOREIGN KEY (item_requirement_id) REFERENCES item_requirements(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quest_quest_requirements (
        quest_id INTEGER NOT NULL,
        quest_requirement_id INTEGER NOT NULL,
        PRIMARY KEY (quest_id, quest_requirement_id),
        FOREIGN KEY (quest_id) REFERENCES quests(id),
        FOREIGN KEY (quest_requirement_id) REFERENCES quest_requirements(id)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS shops (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        location TEXT NOT NULL,
        location_id INTEGER,
        owner TEXT,
        members INTEGER NOT NULL DEFAULT 1,
        region INTEGER CHECK(region IN ({_region_ids}) OR region IS NULL),
        shop_type TEXT NOT NULL DEFAULT 'Other',
        sell_multiplier INTEGER NOT NULL DEFAULT 1000,
        buy_multiplier INTEGER NOT NULL DEFAULT 1000,
        delta INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (location_id) REFERENCES locations(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS npcs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        version TEXT,
        location TEXT,
        x INTEGER,
        y INTEGER,
        options TEXT,
        region INTEGER,
        UNIQUE(name, version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS map_squares (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plane INTEGER NOT NULL,
        region_x INTEGER NOT NULL,
        region_y INTEGER NOT NULL,
        type TEXT NOT NULL DEFAULT 'color',
        image BLOB NOT NULL,
        UNIQUE(plane, region_x, region_y, type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS map_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        src_location TEXT NOT NULL,
        dst_location TEXT NOT NULL,
        src_x INTEGER,
        src_y INTEGER,
        dst_x INTEGER,
        dst_y INTEGER,
        type TEXT,
        description TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS monsters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        version TEXT,
        combat_level INTEGER,
        hitpoints INTEGER,
        attack_speed INTEGER,
        max_hit TEXT,
        attack_style TEXT,
        aggressive INTEGER,
        size INTEGER,
        respawn INTEGER,
        attack_level INTEGER,
        strength_level INTEGER,
        defence_level INTEGER,
        magic_level INTEGER,
        ranged_level INTEGER,
        attack_bonus INTEGER,
        strength_bonus INTEGER,
        magic_attack INTEGER,
        magic_strength INTEGER,
        ranged_attack INTEGER,
        ranged_strength INTEGER,
        defensive_stab INTEGER,
        defensive_slash INTEGER,
        defensive_crush INTEGER,
        defensive_magic INTEGER,
        defensive_light_ranged INTEGER,
        defensive_standard_ranged INTEGER,
        defensive_heavy_ranged INTEGER,
        elemental_weakness_type TEXT,
        elemental_weakness_percent INTEGER,
        immunities INTEGER NOT NULL DEFAULT 0,
        slayer_xp REAL,
        slayer_category TEXT,
        slayer_assigned_by TEXT,
        attributes TEXT,
        examine TEXT,
        members INTEGER,
        UNIQUE(name, version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS monster_locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        monster_id INTEGER NOT NULL,
        location TEXT,
        x INTEGER,
        y INTEGER,
        region INTEGER,
        FOREIGN KEY (monster_id) REFERENCES monsters(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS monster_drops (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        monster_id INTEGER NOT NULL,
        item_name TEXT NOT NULL,
        quantity TEXT,
        rarity TEXT,
        FOREIGN KEY (monster_id) REFERENCES monsters(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS attributions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        table_name TEXT NOT NULL,
        wiki_page TEXT NOT NULL,
        authors TEXT,
        fetched_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS facilities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type INTEGER NOT NULL,
        x INTEGER NOT NULL,
        y INTEGER NOT NULL,
        name TEXT,
        region INTEGER
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        region INTEGER CHECK(region IN ({_region_ids}) OR region IS NULL),
        type TEXT,
        members INTEGER NOT NULL DEFAULT 1,
        x INTEGER,
        y INTEGER,
        facilities INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS location_adjacencies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location_id INTEGER NOT NULL,
        direction TEXT NOT NULL CHECK(direction IN ('north', 'south', 'east', 'west')),
        neighbor TEXT NOT NULL,
        FOREIGN KEY (location_id) REFERENCES locations(id),
        UNIQUE(location_id, direction)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS shop_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_id INTEGER NOT NULL,
        item_name TEXT NOT NULL,
        stock INTEGER NOT NULL DEFAULT 0,
        restock INTEGER NOT NULL DEFAULT 0,
        sell_price INTEGER,
        buy_price INTEGER,
        FOREIGN KEY (shop_id) REFERENCES shops(id),
        UNIQUE(shop_id, item_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_vars (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        var_id INTEGER NOT NULL,
        var_type TEXT NOT NULL CHECK(var_type IN ('varp', 'varbit', 'varc_int', 'varc_str')),
        description TEXT,
        content_tags TEXT,
        functional_tags TEXT,
        UNIQUE(name, var_type)
    )
    """,
]


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_tables(db_path: Path) -> None:
    conn = get_connection(db_path)
    for schema in SCHEMAS:
        conn.execute(schema)
    conn.commit()
    conn.close()
