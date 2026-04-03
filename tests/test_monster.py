import sqlite3

from ragger.enums import Immunity, Region
from ragger.monster import Monster, MonsterDrop, MonsterLocation


def _seed_monsters(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """INSERT INTO monsters (name, version, combat_level, hitpoints, attack_speed,
           aggressive, size, respawn, attack_level, strength_level, defence_level,
           magic_level, ranged_level, immunities, slayer_category, members)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            ("Green dragon", "Level 79", 79, 75, 4, 1, 4, 30, 68, 68, 68, 68, 1, Immunity.BURN.mask, "Green Dragons", 1),
            ("Green dragon", "Level 88", 88, 100, 4, 1, 4, 30, 75, 75, 68, 75, 1, Immunity.BURN.mask, "Green Dragons", 1),
            ("Goblin", "Level 2", 2, 5, 4, 0, 1, 15, 1, 1, 1, 1, 1, 0, None, 0),
        ],
    )
    conn.executemany(
        "INSERT INTO monster_locations (monster_id, location, x, y, region) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "Wilderness", 3300, 3700, Region.WILDERNESS.value),
            (1, "Corsair Cove", 2480, 2887, Region.KANDARIN.value),
            (2, "Wilderness", 3320, 3780, Region.WILDERNESS.value),
            (3, "Lumbridge", 3232, 3226, Region.MISTHALIN.value),
        ],
    )
    conn.executemany(
        "INSERT INTO monster_drops (monster_id, item_name, quantity, rarity) VALUES (?, ?, ?, ?)",
        [
            (1, "Dragon bones", "1", "Always"),
            (1, "Green dragonhide", "1", "Always"),
            (1, "Rune dagger", "1", "3/128"),
            (3, "Bones", "1", "Always"),
        ],
    )
    conn.commit()


def test_all(conn: sqlite3.Connection) -> None:
    _seed_monsters(conn)
    monsters = Monster.all(conn)
    assert len(monsters) == 3
    assert all(isinstance(m, Monster) for m in monsters)


def test_all_filter_region(conn: sqlite3.Connection) -> None:
    _seed_monsters(conn)
    monsters = Monster.all(conn, region=Region.WILDERNESS)
    assert len(monsters) == 2
    names = [(m.name, m.version) for m in monsters]
    assert ("Green dragon", "Level 79") in names
    assert ("Green dragon", "Level 88") in names


def test_by_name(conn: sqlite3.Connection) -> None:
    _seed_monsters(conn)
    monster = Monster.by_name(conn, "Goblin")
    assert monster is not None
    assert monster.combat_level == 2
    assert monster.hitpoints == 5
    assert monster.aggressive is False


def test_by_name_with_version(conn: sqlite3.Connection) -> None:
    _seed_monsters(conn)
    monster = Monster.by_name(conn, "Green dragon", version="Level 88")
    assert monster is not None
    assert monster.hitpoints == 100
    assert monster.combat_level == 88


def test_by_name_not_found(conn: sqlite3.Connection) -> None:
    _seed_monsters(conn)
    assert Monster.by_name(conn, "Nonexistent") is None


def test_by_slayer_category(conn: sqlite3.Connection) -> None:
    _seed_monsters(conn)
    monsters = Monster.by_slayer_category(conn, "Green Dragons")
    assert len(monsters) == 2
    assert all(m.slayer_category == "Green Dragons" for m in monsters)


def test_search(conn: sqlite3.Connection) -> None:
    _seed_monsters(conn)
    results = Monster.search(conn, "dragon")
    assert len(results) == 2
    assert all("dragon" in m.name.lower() for m in results)


def test_locations(conn: sqlite3.Connection) -> None:
    _seed_monsters(conn)
    monster = Monster.by_name(conn, "Green dragon", version="Level 79")
    locs = monster.locations(conn)
    assert len(locs) == 2
    assert all(isinstance(l, MonsterLocation) for l in locs)
    regions = {l.region for l in locs}
    assert Region.WILDERNESS in regions
    assert Region.KANDARIN in regions


def test_drops(conn: sqlite3.Connection) -> None:
    _seed_monsters(conn)
    monster = Monster.by_name(conn, "Green dragon", version="Level 79")
    drops = monster.drops(conn)
    assert len(drops) == 3
    assert all(isinstance(d, MonsterDrop) for d in drops)
    always = [d for d in drops if d.rarity == "Always"]
    assert len(always) == 2


def test_drops_by_name(conn: sqlite3.Connection) -> None:
    _seed_monsters(conn)
    monster = Monster.by_name(conn, "Green dragon", version="Level 79")
    drops = monster.drops_by_name(conn, "Dragon bones")
    assert len(drops) == 1
    assert drops[0].quantity == "1"
    assert drops[0].rarity == "Always"


def test_immunity(conn: sqlite3.Connection) -> None:
    _seed_monsters(conn)
    dragon = Monster.by_name(conn, "Green dragon", version="Level 79")
    assert dragon.has_immunity(Immunity.BURN)
    assert not dragon.has_immunity(Immunity.POISON)
    assert dragon.immunity_list() == [Immunity.BURN]

    goblin = Monster.by_name(conn, "Goblin")
    assert goblin.immunity_list() == []
