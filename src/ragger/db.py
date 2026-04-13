import sqlite3
from pathlib import Path

from ragger.enums import (
    ALL_SKILLS_MASK,
    ActivityType,
    ComparisonOperator,
    DiaryLocation,
    DiaryTier,
    Element,
    EquipmentSlot,
    League,
    Region,
    ShopType,
    Skill,
    Spellbook,
    TaskDifficulty,
)

_skill_ids = ", ".join(str(s.value) for s in Skill)
_region_ids = ", ".join(str(r.value) for r in Region)
_difficulty_ids = ", ".join(str(d.value) for d in TaskDifficulty)
_league_ids = ", ".join(str(l.value) for l in League)
_activity_type_values = ", ".join(f"'{t.value}'" for t in ActivityType)
_diary_location_values = ", ".join(f"'{l.value}'" for l in DiaryLocation)
_diary_tier_values = ", ".join(f"'{t.value}'" for t in DiaryTier)
_equipment_slot_values = ", ".join(f"'{s.value}'" for s in EquipmentSlot)
_comparison_operator_values = ", ".join(f"'{o.value}'" for o in ComparisonOperator)
_spellbook_values = ", ".join(f"'{s.value}'" for s in Spellbook)
_element_values = ", ".join(f"'{e.value}'" for e in Element)

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
        name TEXT NOT NULL UNIQUE,
        members INTEGER,
        tradeable INTEGER,
        weight REAL,
        examine TEXT,
        value INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS item_game_ids (
        item_id INTEGER NOT NULL,
        game_id INTEGER NOT NULL,
        PRIMARY KEY (item_id, game_id),
        FOREIGN KEY (item_id) REFERENCES items(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS item_aliases (
        item_id INTEGER NOT NULL,
        alias TEXT NOT NULL,
        PRIMARY KEY (item_id, alias),
        FOREIGN KEY (item_id) REFERENCES items(id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_item_aliases_alias ON item_aliases(alias)
    """,
    """
    CREATE TABLE IF NOT EXISTS quest_aliases (
        quest_id INTEGER NOT NULL,
        alias TEXT NOT NULL,
        PRIMARY KEY (quest_id, alias),
        FOREIGN KEY (quest_id) REFERENCES quests(id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_quest_aliases_alias ON quest_aliases(alias)
    """,
    """
    CREATE TABLE IF NOT EXISTS npc_aliases (
        npc_name TEXT NOT NULL,
        alias TEXT NOT NULL,
        PRIMARY KEY (npc_name, alias)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_npc_aliases_alias ON npc_aliases(alias)
    """,
    """
    CREATE TABLE IF NOT EXISTS monster_aliases (
        monster_name TEXT NOT NULL,
        alias TEXT NOT NULL,
        PRIMARY KEY (monster_name, alias)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_monster_aliases_alias ON monster_aliases(alias)
    """,
    """
    CREATE TABLE IF NOT EXISTS equipment_aliases (
        equipment_name TEXT NOT NULL,
        alias TEXT NOT NULL,
        PRIMARY KEY (equipment_name, alias)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_equipment_aliases_alias ON equipment_aliases(alias)
    """,
    """
    CREATE TABLE IF NOT EXISTS physical_currencies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        item_id INTEGER NOT NULL,
        FOREIGN KEY (item_id) REFERENCES items(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS virtual_currencies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        varbit_id INTEGER,
        FOREIGN KEY (varbit_id) REFERENCES game_vars(id)
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
    CREATE TABLE IF NOT EXISTS league_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        difficulty INTEGER NOT NULL CHECK(difficulty IN ({_difficulty_ids})),
        region INTEGER NOT NULL CHECK(region IN ({_region_ids})),
        league INTEGER NOT NULL CHECK(league IN ({_league_ids})),
        UNIQUE(name, league)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS requirement_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS group_skill_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        skill INTEGER NOT NULL CHECK(skill IN ({_skill_ids})),
        level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 99),
        boostable INTEGER NOT NULL DEFAULT 0,
        operator TEXT NOT NULL DEFAULT '>=' CHECK(operator IN ({_comparison_operator_values})),
        FOREIGN KEY (group_id) REFERENCES requirement_groups(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS group_quest_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        required_quest_id INTEGER NOT NULL,
        partial INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (group_id) REFERENCES requirement_groups(id),
        FOREIGN KEY (required_quest_id) REFERENCES quests(id)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS group_quest_point_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        points INTEGER NOT NULL,
        operator TEXT NOT NULL DEFAULT '>=' CHECK(operator IN ({_comparison_operator_values})),
        FOREIGN KEY (group_id) REFERENCES requirement_groups(id)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS group_item_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        operator TEXT NOT NULL DEFAULT '>=' CHECK(operator IN ({_comparison_operator_values})),
        FOREIGN KEY (group_id) REFERENCES requirement_groups(id),
        FOREIGN KEY (item_id) REFERENCES items(id)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS group_diary_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        location TEXT NOT NULL CHECK(location IN ({_diary_location_values})),
        tier TEXT NOT NULL CHECK(tier IN ({_diary_tier_values})),
        FOREIGN KEY (group_id) REFERENCES requirement_groups(id)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS group_region_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        region INTEGER NOT NULL CHECK(region IN ({_region_ids})),
        FOREIGN KEY (group_id) REFERENCES requirement_groups(id)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS group_equipment_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        slot TEXT NOT NULL CHECK(slot IN ({_equipment_slot_values})),
        quantity INTEGER NOT NULL DEFAULT 1,
        operator TEXT NOT NULL DEFAULT '>=' CHECK(operator IN ({_comparison_operator_values})),
        FOREIGN KEY (group_id) REFERENCES requirement_groups(id),
        FOREIGN KEY (item_id) REFERENCES items(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quest_requirement_groups (
        quest_id INTEGER NOT NULL,
        group_id INTEGER NOT NULL,
        PRIMARY KEY (quest_id, group_id),
        FOREIGN KEY (quest_id) REFERENCES quests(id),
        FOREIGN KEY (group_id) REFERENCES requirement_groups(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS league_task_requirement_groups (
        league_task_id INTEGER NOT NULL,
        group_id INTEGER NOT NULL,
        PRIMARY KEY (league_task_id, group_id),
        FOREIGN KEY (league_task_id) REFERENCES league_tasks(id),
        FOREIGN KEY (group_id) REFERENCES requirement_groups(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS diary_task_requirement_groups (
        diary_task_id INTEGER NOT NULL,
        group_id INTEGER NOT NULL,
        PRIMARY KEY (diary_task_id, group_id),
        FOREIGN KEY (diary_task_id) REFERENCES diary_tasks(id),
        FOREIGN KEY (group_id) REFERENCES requirement_groups(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS equipment_requirement_groups (
        equipment_id INTEGER NOT NULL,
        group_id INTEGER NOT NULL,
        PRIMARY KEY (equipment_id, group_id),
        FOREIGN KEY (equipment_id) REFERENCES equipment(id),
        FOREIGN KEY (group_id) REFERENCES requirement_groups(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS monster_requirement_groups (
        monster_id INTEGER NOT NULL,
        group_id INTEGER NOT NULL,
        PRIMARY KEY (monster_id, group_id),
        FOREIGN KEY (monster_id) REFERENCES monsters(id),
        FOREIGN KEY (group_id) REFERENCES requirement_groups(id)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS group_varbit_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        var_id INTEGER NOT NULL,
        value INTEGER NOT NULL,
        operator TEXT NOT NULL DEFAULT '==' CHECK(operator IN ({_comparison_operator_values})),
        FOREIGN KEY (group_id) REFERENCES requirement_groups(id),
        FOREIGN KEY (var_id) REFERENCES game_vars(id)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS group_varp_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        var_id INTEGER NOT NULL,
        value INTEGER NOT NULL,
        operator TEXT NOT NULL DEFAULT '==' CHECK(operator IN ({_comparison_operator_values})),
        FOREIGN KEY (group_id) REFERENCES requirement_groups(id),
        FOREIGN KEY (var_id) REFERENCES game_vars(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS map_link_requirement_groups (
        map_link_id INTEGER NOT NULL,
        group_id INTEGER NOT NULL,
        PRIMARY KEY (map_link_id, group_id),
        FOREIGN KEY (map_link_id) REFERENCES map_links(id),
        FOREIGN KEY (group_id) REFERENCES requirement_groups(id)
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
    CREATE TABLE IF NOT EXISTS quest_items (
        quest_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        PRIMARY KEY (quest_id, item_id),
        FOREIGN KEY (quest_id) REFERENCES quests(id),
        FOREIGN KEY (item_id) REFERENCES items(id)
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
        physical_currency_id INTEGER REFERENCES physical_currencies(id),
        virtual_currency_id INTEGER REFERENCES virtual_currencies(id),
        CHECK(NOT (physical_currency_id IS NOT NULL AND virtual_currency_id IS NOT NULL)),
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
    CREATE TABLE IF NOT EXISTS npc_locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        x INTEGER NOT NULL,
        y INTEGER NOT NULL,
        UNIQUE(game_id, x, y)
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
    CREATE TABLE IF NOT EXISTS blobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location_id INTEGER NOT NULL,
        tile_count INTEGER NOT NULL,
        FOREIGN KEY (location_id) REFERENCES locations(id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_blobs_location_id ON blobs(location_id)",
    """
    CREATE TABLE IF NOT EXISTS ports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ridge_location_a_id INTEGER NOT NULL,
        ridge_location_b_id INTEGER NOT NULL,
        side_location_id INTEGER NOT NULL,
        blob_id INTEGER NOT NULL,
        sample_start INTEGER NOT NULL,
        sample_end INTEGER NOT NULL,
        rep_x INTEGER NOT NULL,
        rep_y INTEGER NOT NULL,
        FOREIGN KEY (ridge_location_a_id) REFERENCES locations(id),
        FOREIGN KEY (ridge_location_b_id) REFERENCES locations(id),
        FOREIGN KEY (side_location_id) REFERENCES locations(id),
        FOREIGN KEY (blob_id) REFERENCES blobs(id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_ports_blob ON ports(blob_id)",
    "CREATE INDEX IF NOT EXISTS idx_ports_ridge ON ports(ridge_location_a_id, ridge_location_b_id)",
    "CREATE INDEX IF NOT EXISTS idx_ports_side ON ports(side_location_id)",
    """
    CREATE TABLE IF NOT EXISTS port_transits (
        src_port_id INTEGER NOT NULL,
        dst_port_id INTEGER NOT NULL,
        distance INTEGER NOT NULL,
        PRIMARY KEY (src_port_id, dst_port_id),
        FOREIGN KEY (src_port_id) REFERENCES ports(id),
        FOREIGN KEY (dst_port_id) REFERENCES ports(id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_port_transits_src ON port_transits(src_port_id)",
    """
    CREATE TABLE IF NOT EXISTS port_crossings (
        src_port_id INTEGER NOT NULL,
        dst_port_id INTEGER NOT NULL,
        distance INTEGER NOT NULL,
        PRIMARY KEY (src_port_id, dst_port_id),
        FOREIGN KEY (src_port_id) REFERENCES ports(id),
        FOREIGN KEY (dst_port_id) REFERENCES ports(id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_port_crossings_src ON port_crossings(src_port_id)",
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
        description TEXT,
        src_blob_id INTEGER REFERENCES blobs(id),
        dst_blob_id INTEGER REFERENCES blobs(id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_map_links_src_blob ON map_links(src_blob_id)",
    "CREATE INDEX IF NOT EXISTS idx_map_links_dst_blob ON map_links(dst_blob_id)",
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
    CREATE TABLE IF NOT EXISTS location_aliases (
        location_id INTEGER NOT NULL,
        alias TEXT NOT NULL,
        PRIMARY KEY (location_id, alias),
        FOREIGN KEY (location_id) REFERENCES locations(id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_location_aliases_alias ON location_aliases(alias)
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
    f"""
    CREATE TABLE IF NOT EXISTS activities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        type TEXT NOT NULL DEFAULT 'Activity' CHECK(type IN ({_activity_type_values})),
        members INTEGER NOT NULL DEFAULT 1,
        location TEXT,
        location_id INTEGER,
        x INTEGER,
        y INTEGER,
        players TEXT,
        skills INTEGER NOT NULL DEFAULT 0,
        region INTEGER CHECK(region IN ({_region_ids}) OR region IS NULL),
        FOREIGN KEY (location_id) REFERENCES locations(id)
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
    """
    CREATE TABLE IF NOT EXISTS equipment (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        version TEXT,
        item_id INTEGER,
        slot TEXT,
        two_handed INTEGER NOT NULL DEFAULT 0,
        attack_stab INTEGER,
        attack_slash INTEGER,
        attack_crush INTEGER,
        attack_magic INTEGER,
        attack_ranged INTEGER,
        defence_stab INTEGER,
        defence_slash INTEGER,
        defence_crush INTEGER,
        defence_magic INTEGER,
        defence_ranged INTEGER,
        melee_strength INTEGER,
        ranged_strength INTEGER,
        magic_damage INTEGER,
        prayer INTEGER,
        speed INTEGER,
        attack_range INTEGER,
        combat_style TEXT,
        FOREIGN KEY (item_id) REFERENCES items(id),
        UNIQUE(name, version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        members INTEGER NOT NULL DEFAULT 1,
        ticks INTEGER,
        notes TEXT
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS action_output_experience (
        action_id INTEGER NOT NULL,
        skill INTEGER NOT NULL CHECK(skill IN ({_skill_ids})),
        xp REAL NOT NULL,
        FOREIGN KEY (action_id) REFERENCES actions(id),
        PRIMARY KEY (action_id, skill)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS action_input_items (
        action_id INTEGER NOT NULL,
        item_id INTEGER,
        item_name TEXT NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (action_id) REFERENCES actions(id),
        FOREIGN KEY (item_id) REFERENCES items(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS action_input_objects (
        action_id INTEGER NOT NULL,
        object_name TEXT NOT NULL,
        FOREIGN KEY (action_id) REFERENCES actions(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS action_input_currencies (
        action_id INTEGER NOT NULL,
        currency TEXT NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (action_id) REFERENCES actions(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS action_output_items (
        action_id INTEGER NOT NULL,
        item_id INTEGER,
        item_name TEXT NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (action_id) REFERENCES actions(id),
        FOREIGN KEY (item_id) REFERENCES items(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS action_output_objects (
        action_id INTEGER NOT NULL,
        object_name TEXT NOT NULL,
        FOREIGN KEY (action_id) REFERENCES actions(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS action_triggers (
        action_id INTEGER NOT NULL,
        trigger_type INTEGER NOT NULL,
        source_id INTEGER,
        target_id INTEGER NOT NULL,
        op TEXT NOT NULL,
        FOREIGN KEY (action_id) REFERENCES actions(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS action_requirement_groups (
        action_id INTEGER NOT NULL,
        group_id INTEGER NOT NULL,
        PRIMARY KEY (action_id, group_id),
        FOREIGN KEY (action_id) REFERENCES actions(id),
        FOREIGN KEY (group_id) REFERENCES requirement_groups(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_actions (
        source TEXT NOT NULL,
        action_id INTEGER NOT NULL,
        PRIMARY KEY (source, action_id),
        FOREIGN KEY (action_id) REFERENCES actions(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS object_locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id INTEGER NOT NULL,
        x INTEGER NOT NULL,
        y INTEGER NOT NULL,
        plane INTEGER NOT NULL DEFAULT 0,
        type INTEGER NOT NULL,
        orientation INTEGER NOT NULL,
        UNIQUE(game_id, x, y, plane, type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dialogue_pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL UNIQUE,
        page_type TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dialogue_nodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        page_id INTEGER NOT NULL,
        parent_id INTEGER,
        sort_order INTEGER NOT NULL,
        depth INTEGER NOT NULL,
        node_type TEXT NOT NULL,
        speaker TEXT,
        text TEXT,
        section TEXT,
        continue_target_id INTEGER,
        FOREIGN KEY (page_id) REFERENCES dialogue_pages(id),
        FOREIGN KEY (parent_id) REFERENCES dialogue_nodes(id),
        FOREIGN KEY (continue_target_id) REFERENCES dialogue_nodes(id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_dialogue_nodes_page_id ON dialogue_nodes(page_id)",
    "CREATE INDEX IF NOT EXISTS idx_dialogue_nodes_parent_id ON dialogue_nodes(parent_id)",
    """
    CREATE TABLE IF NOT EXISTS dialogue_instructions (
        page_id INTEGER NOT NULL,
        addr INTEGER NOT NULL,
        section TEXT NOT NULL,
        op TEXT NOT NULL,
        text TEXT NOT NULL DEFAULT '',
        speaker TEXT,
        fallthrough INTEGER NOT NULL DEFAULT 1,
        targets TEXT NOT NULL DEFAULT '[]',
        target_labels TEXT NOT NULL DEFAULT '[]',
        target_predicates TEXT NOT NULL DEFAULT '[]',
        PRIMARY KEY (page_id, addr),
        FOREIGN KEY (page_id) REFERENCES dialogue_pages(id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_dialogue_instructions_section ON dialogue_instructions(page_id, section)",
    "CREATE INDEX IF NOT EXISTS idx_dialogue_instructions_op ON dialogue_instructions(op)",
    "CREATE INDEX IF NOT EXISTS idx_dialogue_instructions_speaker ON dialogue_instructions(speaker)",
    """
    CREATE TABLE IF NOT EXISTS dialogue_tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        node_id INTEGER NOT NULL,
        entity_type TEXT NOT NULL,
        entity_name TEXT NOT NULL,
        entity_id INTEGER,
        FOREIGN KEY (node_id) REFERENCES dialogue_nodes(id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_dialogue_tags_node_id ON dialogue_tags(node_id)",
    "CREATE INDEX IF NOT EXISTS idx_dialogue_tags_entity ON dialogue_tags(entity_type, entity_name)",
    f"""
    CREATE TABLE IF NOT EXISTS ground_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_name TEXT NOT NULL,
        item_id INTEGER,
        location TEXT NOT NULL,
        location_id INTEGER,
        members INTEGER NOT NULL DEFAULT 1,
        x INTEGER NOT NULL,
        y INTEGER NOT NULL,
        plane INTEGER NOT NULL DEFAULT 0,
        region INTEGER CHECK(region IN ({_region_ids}) OR region IS NULL),
        FOREIGN KEY (item_id) REFERENCES items(id),
        FOREIGN KEY (location_id) REFERENCES locations(id),
        UNIQUE(item_name, x, y)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS npc_dialogues (
        npc_id INTEGER NOT NULL,
        page_id INTEGER NOT NULL,
        PRIMARY KEY (npc_id, page_id),
        FOREIGN KEY (npc_id) REFERENCES npcs(id),
        FOREIGN KEY (page_id) REFERENCES dialogue_pages(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quest_dialogues (
        quest_id INTEGER NOT NULL,
        page_id INTEGER NOT NULL,
        PRIMARY KEY (quest_id, page_id),
        FOREIGN KEY (quest_id) REFERENCES quests(id),
        FOREIGN KEY (page_id) REFERENCES dialogue_pages(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS wiki_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        page_count INTEGER NOT NULL DEFAULT 0,
        subcat_count INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS wiki_category_parents (
        category_id INTEGER NOT NULL,
        parent_id INTEGER NOT NULL,
        PRIMARY KEY (category_id, parent_id),
        FOREIGN KEY (category_id) REFERENCES wiki_categories(id),
        FOREIGN KEY (parent_id) REFERENCES wiki_categories(id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_wiki_category_parents_parent
        ON wiki_category_parents(parent_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS page_categories (
        page_title TEXT NOT NULL,
        category_id INTEGER NOT NULL,
        PRIMARY KEY (page_title, category_id),
        FOREIGN KEY (category_id) REFERENCES wiki_categories(id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_page_categories_category
        ON page_categories(category_id)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS combat_spells (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        members INTEGER NOT NULL DEFAULT 0,
        level INTEGER NOT NULL,
        spellbook TEXT NOT NULL CHECK(spellbook IN ({_spellbook_values})),
        experience REAL NOT NULL DEFAULT 0,
        speed INTEGER,
        cooldown INTEGER,
        element TEXT CHECK(element IN ({_element_values}) OR element IS NULL),
        max_damage INTEGER,
        description TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS combat_spell_runes (
        spell_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (spell_id, item_id),
        FOREIGN KEY (spell_id) REFERENCES combat_spells(id),
        FOREIGN KEY (item_id) REFERENCES items(id)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS utility_spells (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        members INTEGER NOT NULL DEFAULT 0,
        level INTEGER NOT NULL,
        spellbook TEXT NOT NULL CHECK(spellbook IN ({_spellbook_values})),
        experience REAL NOT NULL DEFAULT 0,
        speed INTEGER,
        cooldown INTEGER,
        description TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS utility_spell_runes (
        spell_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (spell_id, item_id),
        FOREIGN KEY (spell_id) REFERENCES utility_spells(id),
        FOREIGN KEY (item_id) REFERENCES items(id)
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS teleport_spells (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        members INTEGER NOT NULL DEFAULT 0,
        level INTEGER NOT NULL,
        spellbook TEXT NOT NULL CHECK(spellbook IN ({_spellbook_values})),
        experience REAL NOT NULL DEFAULT 0,
        speed INTEGER,
        destination TEXT,
        dst_x INTEGER,
        dst_y INTEGER,
        lectern TEXT,
        description TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS teleport_spell_runes (
        spell_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (spell_id, item_id),
        FOREIGN KEY (spell_id) REFERENCES teleport_spells(id),
        FOREIGN KEY (item_id) REFERENCES items(id)
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
