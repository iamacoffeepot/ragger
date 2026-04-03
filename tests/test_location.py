import math
import sqlite3

from ragger.enums import Facility, Region
from ragger.location import Adjacency, DistanceMetric, Location


def _seed_locations(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO locations (name, region, type, members, x, y) VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("Lumbridge", Region.MISTHALIN.value, "settlement", 0, 3188, 3220),
            ("Varrock", Region.MISTHALIN.value, "settlement", 0, 3210, 3448),
            ("Aldarin", Region.VARLAMORE.value, "Island", 1, 1391, 2935),
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


def test_within_returns_self_at_zero(conn: sqlite3.Connection) -> None:
    _seed_locations(conn)
    loc = Location.by_name(conn, "Lumbridge")
    results = loc.within(conn, 0)
    assert len(results) == 1
    assert results[0][0].name == "Lumbridge"
    assert results[0][1] == 0


def test_within_one_hop(conn: sqlite3.Connection) -> None:
    _seed_locations(conn)
    loc = Location.by_name(conn, "Lumbridge")
    results = loc.within(conn, 1)
    names = {r[0].name: r[1] for r in results}
    assert names["Lumbridge"] == 0
    assert names["Varrock"] == 1
    # Al Kharid is adjacent but not in DB, so not reachable
    assert "Al Kharid" not in names


def test_within_multi_hop(conn: sqlite3.Connection) -> None:
    _seed_locations(conn)
    # Add a chain: Varrock --north--> Wilderness
    conn.execute(
        "INSERT INTO locations (name, region, type, members, x, y) VALUES (?, ?, ?, ?, ?, ?)",
        ("Wilderness", Region.WILDERNESS.value, "area", 1, 3200, 3800),
    )
    wilderness_id = conn.execute("SELECT id FROM locations WHERE name = 'Wilderness'").fetchone()[0]
    varrock_id = conn.execute("SELECT id FROM locations WHERE name = 'Varrock'").fetchone()[0]
    conn.execute(
        "INSERT INTO location_adjacencies (location_id, direction, neighbor) VALUES (?, ?, ?)",
        (varrock_id, "north", "Wilderness"),
    )
    conn.execute(
        "INSERT INTO location_adjacencies (location_id, direction, neighbor) VALUES (?, ?, ?)",
        (wilderness_id, "south", "Varrock"),
    )
    conn.commit()

    loc = Location.by_name(conn, "Lumbridge")
    # Wilderness is 2 hops from Lumbridge
    results_1 = loc.within(conn, 1)
    assert "Wilderness" not in [r[0].name for r in results_1]

    results_2 = loc.within(conn, 2)
    names = {r[0].name: r[1] for r in results_2}
    assert names["Wilderness"] == 2
    assert names["Varrock"] == 1
    assert names["Lumbridge"] == 0


def test_within_shortest_path(conn: sqlite3.Connection) -> None:
    _seed_locations(conn)
    # Add shortcut: Lumbridge --west--> Aldarin (normally far away)
    conn.execute(
        "INSERT INTO location_adjacencies (location_id, direction, neighbor) VALUES (?, ?, ?)",
        (1, "west", "Aldarin"),
    )
    # Also: Varrock --east--> Aldarin (so Aldarin reachable via 2 hops too)
    conn.execute(
        "INSERT INTO location_adjacencies (location_id, direction, neighbor) VALUES (?, ?, ?)",
        (2, "east", "Aldarin"),
    )
    conn.commit()

    loc = Location.by_name(conn, "Lumbridge")
    results = loc.within(conn, 2)
    names = {r[0].name: r[1] for r in results}
    # Aldarin should be 1 hop (direct), not 2 (via Varrock)
    assert names["Aldarin"] == 1


def test_nearby_chebyshev(conn: sqlite3.Connection) -> None:
    _seed_locations(conn)
    loc = Location.by_name(conn, "Lumbridge")
    # Varrock is dx=22, dy=228 -> chebyshev = 228
    results = loc.nearby(conn, 300, metric=DistanceMetric.CHEBYSHEV)
    names = [r[0].name for r in results]
    assert "Varrock" in names
    # Aldarin is dx=1797, dy=285 -> chebyshev = 1797, too far
    assert "Aldarin" not in names


def test_nearby_manhattan(conn: sqlite3.Connection) -> None:
    _seed_locations(conn)
    loc = Location.by_name(conn, "Lumbridge")
    # Varrock: dx=22, dy=228 -> manhattan = 250
    results = loc.nearby(conn, 250, metric=DistanceMetric.MANHATTAN)
    assert len(results) == 1
    assert results[0][0].name == "Varrock"
    assert results[0][1] == 250


def test_nearby_euclidean(conn: sqlite3.Connection) -> None:
    _seed_locations(conn)
    loc = Location.by_name(conn, "Lumbridge")
    # Varrock: sqrt(22^2 + 228^2) = sqrt(484 + 51984) = sqrt(52468) ~ 229.06
    results = loc.nearby(conn, 230, metric=DistanceMetric.EUCLIDEAN)
    assert len(results) == 1
    assert results[0][0].name == "Varrock"
    expected = math.sqrt(22**2 + 228**2)
    assert abs(results[0][1] - expected) < 0.01


def test_nearby_default_is_chebyshev(conn: sqlite3.Connection) -> None:
    _seed_locations(conn)
    loc = Location.by_name(conn, "Lumbridge")
    results_default = loc.nearby(conn, 300)
    results_chebyshev = loc.nearby(conn, 300, metric=DistanceMetric.CHEBYSHEV)
    assert len(results_default) == len(results_chebyshev)
    assert [r[0].name for r in results_default] == [r[0].name for r in results_chebyshev]


def test_nearby_no_coordinates(conn: sqlite3.Connection) -> None:
    _seed_locations(conn)
    # Insert a location without coordinates
    conn.execute(
        "INSERT INTO locations (name, region, type, members) VALUES (?, ?, ?, ?)",
        ("Mystery", Region.MISTHALIN.value, "dungeon", 1),
    )
    conn.commit()
    loc = Location.by_name(conn, "Mystery")
    assert loc.nearby(conn, 1000) == []


def test_nearby_excludes_self(conn: sqlite3.Connection) -> None:
    _seed_locations(conn)
    loc = Location.by_name(conn, "Lumbridge")
    results = loc.nearby(conn, 100000)
    names = [r[0].name for r in results]
    assert "Lumbridge" not in names


def test_nearest(conn: sqlite3.Connection) -> None:
    _seed_locations(conn)
    # (3190, 3225) is close to Lumbridge (3188, 3220)
    loc = Location.nearest(conn, 3190, 3225)
    assert loc is not None
    assert loc.name == "Lumbridge"


def test_nearest_no_locations(conn: sqlite3.Connection) -> None:
    # Empty DB, no locations with coords
    assert Location.nearest(conn, 100, 100) is None


def test_with_facilities_single(conn: sqlite3.Connection) -> None:
    _seed_locations(conn)
    conn.execute(
        "UPDATE locations SET facilities = ? WHERE name = 'Lumbridge'",
        (Facility.BANK.mask | Facility.FURNACE.mask,),
    )
    conn.commit()

    locs = Location.with_facilities(conn, [Facility.BANK])
    assert len(locs) == 1
    assert locs[0].name == "Lumbridge"
    assert locs[0].has_facility(Facility.BANK)
    assert locs[0].has_facility(Facility.FURNACE)


def test_with_facilities_multiple(conn: sqlite3.Connection) -> None:
    _seed_locations(conn)
    conn.execute(
        "UPDATE locations SET facilities = ? WHERE name = 'Lumbridge'",
        (Facility.BANK.mask | Facility.FURNACE.mask,),
    )
    conn.execute(
        "UPDATE locations SET facilities = ? WHERE name = 'Varrock'",
        (Facility.BANK.mask | Facility.ANVIL.mask,),
    )
    conn.commit()

    # Both have banks
    locs = Location.with_facilities(conn, [Facility.BANK])
    assert len(locs) == 2

    # Only Lumbridge has bank + furnace
    locs = Location.with_facilities(conn, [Facility.BANK, Facility.FURNACE])
    assert len(locs) == 1
    assert locs[0].name == "Lumbridge"


def test_with_facilities_region_filter(conn: sqlite3.Connection) -> None:
    _seed_locations(conn)
    conn.execute(
        "UPDATE locations SET facilities = ? WHERE name = 'Lumbridge'",
        (Facility.BANK.mask,),
    )
    conn.execute(
        "UPDATE locations SET facilities = ? WHERE name = 'Aldarin'",
        (Facility.BANK.mask,),
    )
    conn.commit()

    locs = Location.with_facilities(conn, [Facility.BANK], region=Region.VARLAMORE)
    assert len(locs) == 1
    assert locs[0].name == "Aldarin"


def test_facility_list(conn: sqlite3.Connection) -> None:
    _seed_locations(conn)
    conn.execute(
        "UPDATE locations SET facilities = ? WHERE name = 'Lumbridge'",
        (Facility.BANK.mask | Facility.RANGE.mask | Facility.ALTAR.mask,),
    )
    conn.commit()

    loc = Location.by_name(conn, "Lumbridge")
    facilities = loc.facility_list()
    assert Facility.BANK in facilities
    assert Facility.RANGE in facilities
    assert Facility.ALTAR in facilities
    assert Facility.FURNACE not in facilities
