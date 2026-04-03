import sqlite3

from ragger.enums import Facility
from ragger.facility import FacilityEntry
from ragger.location import DistanceMetric


def _seed_facilities(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO facilities (type, x, y, name) VALUES (?, ?, ?, ?)",
        [
            (Facility.BANK.value, 3185, 3441, "Varrock west bank"),
            (Facility.BANK.value, 3253, 3420, "Varrock east bank"),
            (Facility.FURNACE.value, 3109, 3499, "Edgeville furnace"),
            (Facility.ANVIL.value, 3188, 3427, "Varrock anvil"),
            (Facility.ALTAR.value, 3259, 3381, "Chaos altar"),
        ],
    )
    conn.commit()


def test_all(conn: sqlite3.Connection) -> None:
    _seed_facilities(conn)
    entries = FacilityEntry.all(conn)
    assert len(entries) == 5
    assert all(isinstance(e, FacilityEntry) for e in entries)


def test_all_filter_type(conn: sqlite3.Connection) -> None:
    _seed_facilities(conn)
    banks = FacilityEntry.all(conn, facility_type=Facility.BANK)
    assert len(banks) == 2
    assert all(b.type == Facility.BANK for b in banks)


def test_nearest(conn: sqlite3.Connection) -> None:
    _seed_facilities(conn)
    # Near Varrock west bank (3185, 3441)
    entry = FacilityEntry.nearest(conn, 3186, 3440)
    assert entry is not None
    assert entry.name == "Varrock west bank"


def test_nearest_by_type(conn: sqlite3.Connection) -> None:
    _seed_facilities(conn)
    # Nearest furnace to Varrock center
    entry = FacilityEntry.nearest(conn, 3210, 3430, facility_type=Facility.FURNACE)
    assert entry is not None
    assert entry.name == "Edgeville furnace"


def test_nearest_empty(conn: sqlite3.Connection) -> None:
    _seed_facilities(conn)
    assert FacilityEntry.nearest(conn, 100, 100, facility_type=Facility.LOOM) is None


def test_nearby(conn: sqlite3.Connection) -> None:
    _seed_facilities(conn)
    # Everything within 100 tiles of Varrock center
    results = FacilityEntry.nearby(conn, 3210, 3430, 100)
    assert len(results) == 4  # both banks, anvil, altar (furnace is ~100+ away)
    names = [r[0].name for r in results]
    assert "Varrock west bank" in names
    assert "Varrock east bank" in names
    assert "Varrock anvil" in names


def test_nearby_by_type(conn: sqlite3.Connection) -> None:
    _seed_facilities(conn)
    results = FacilityEntry.nearby(conn, 3210, 3430, 100, facility_type=Facility.BANK)
    assert len(results) == 2
    assert all(r[0].type == Facility.BANK for r in results)


def test_nearby_sorted_by_distance(conn: sqlite3.Connection) -> None:
    _seed_facilities(conn)
    results = FacilityEntry.nearby(conn, 3185, 3441, 200)
    distances = [r[1] for r in results]
    assert distances == sorted(distances)


def test_nearby_manhattan(conn: sqlite3.Connection) -> None:
    _seed_facilities(conn)
    # Varrock anvil is at (3188, 3427), dx=2, dy=14 from (3186, 3441)
    # Manhattan = 16, Chebyshev = 14
    results = FacilityEntry.nearby(conn, 3186, 3441, 15, facility_type=Facility.ANVIL, metric=DistanceMetric.MANHATTAN)
    assert len(results) == 0  # manhattan 16 > 15

    results = FacilityEntry.nearby(conn, 3186, 3441, 16, facility_type=Facility.ANVIL, metric=DistanceMetric.MANHATTAN)
    assert len(results) == 1
