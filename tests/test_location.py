import sqlite3

from clogger.enums import Region
from clogger.location import Adjacency, Location


def _seed_locations(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO locations (name, region, type, members) VALUES (?, ?, ?, ?)",
        [
            ("Lumbridge", Region.MISTHALIN.value, "settlement", 0),
            ("Varrock", Region.MISTHALIN.value, "settlement", 0),
            ("Aldarin", Region.VARLAMORE.value, "Island", 1),
        ],
    )
    conn.executemany(
        "INSERT INTO location_adjacencies (location_id, direction, neighbor) VALUES (?, ?, ?)",
        [
            (1, "north", "Varrock"),
            (1, "east", "Al Kharid"),
            (2, "south", "Lumbridge"),
        ],
    )
    conn.commit()


def test_all(conn: sqlite3.Connection) -> None:
    _seed_locations(conn)
    locations = Location.all(conn)
    assert len(locations) == 3
    assert all(isinstance(loc, Location) for loc in locations)


def test_all_filter_region(conn: sqlite3.Connection) -> None:
    _seed_locations(conn)
    locations = Location.all(conn, region=Region.MISTHALIN)
    assert len(locations) == 2
    assert all(loc.region == Region.MISTHALIN for loc in locations)


def test_by_name(conn: sqlite3.Connection) -> None:
    _seed_locations(conn)
    loc = Location.by_name(conn, "Lumbridge")
    assert loc is not None
    assert loc.region == Region.MISTHALIN
    assert loc.type == "settlement"
    assert loc.members is False


def test_by_name_not_found(conn: sqlite3.Connection) -> None:
    _seed_locations(conn)
    assert Location.by_name(conn, "Nonexistent") is None


def test_adjacencies(conn: sqlite3.Connection) -> None:
    _seed_locations(conn)
    loc = Location.by_name(conn, "Lumbridge")
    adjs = loc.adjacencies(conn)
    assert len(adjs) == 2
    assert all(isinstance(a, Adjacency) for a in adjs)
    directions = {a.direction: a.neighbor for a in adjs}
    assert directions["north"] == "Varrock"
    assert directions["east"] == "Al Kharid"


def test_neighbors(conn: sqlite3.Connection) -> None:
    _seed_locations(conn)
    loc = Location.by_name(conn, "Lumbridge")
    neighbors = loc.neighbors(conn)
    assert neighbors["north"] is not None
    assert neighbors["north"].name == "Varrock"
    # Al Kharid is not in the DB
    assert neighbors["east"] is None
