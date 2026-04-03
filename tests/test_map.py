import sqlite3

from ragger.enums import MapLinkType
from ragger.map import MapLink


def _seed_links(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """INSERT INTO map_links (src_location, dst_location, src_x, src_y, dst_x, dst_y, type, description)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            ("Lumbridge", "Varrock", 3188, 3220, 3210, 3448, "walkable", "Voronoi walkable"),
            ("Varrock", "Lumbridge", 3210, 3448, 3188, 3220, "walkable", "Voronoi walkable"),
            ("Lumbridge", "Al Kharid", 3188, 3220, 3293, 3163, "walkable", "Voronoi walkable"),
            ("Al Kharid", "Lumbridge", 3293, 3163, 3188, 3220, "walkable", "Voronoi walkable"),
            ("ANYWHERE", "Varrock", 0, 0, 3213, 3424, "teleport", "Varrock Teleport (Magic 25)"),
            ("Lumbridge", "Dragon Nest", 3188, 3220, 1246, 9500, "entrance", "Entrance to Dragon Nest"),
            ("Auburn Valley", "Avium Savannah", 1430, 3323, 1651, 3010, "fairy_ring", "Fairy ring AIS -> AJP"),
        ],
    )
    conn.commit()


def test_all(conn: sqlite3.Connection) -> None:
    _seed_links(conn)
    links = MapLink.all(conn)
    assert len(links) == 7


def test_all_filter_type(conn: sqlite3.Connection) -> None:
    _seed_links(conn)
    links = MapLink.all(conn, link_type=MapLinkType.WALKABLE)
    assert len(links) == 4
    assert all(l.link_type == MapLinkType.WALKABLE for l in links)


def test_departing(conn: sqlite3.Connection) -> None:
    _seed_links(conn)
    links = MapLink.departing(conn, "Lumbridge")
    assert len(links) == 3
    destinations = {l.dst_location for l in links}
    assert "Varrock" in destinations
    assert "Al Kharid" in destinations
    assert "Dragon Nest" in destinations


def test_departing_with_type(conn: sqlite3.Connection) -> None:
    _seed_links(conn)
    links = MapLink.departing(conn, "Lumbridge", link_type=MapLinkType.WALKABLE)
    assert len(links) == 2


def test_arriving(conn: sqlite3.Connection) -> None:
    _seed_links(conn)
    links = MapLink.arriving(conn, "Varrock")
    assert len(links) == 2
    types = {l.link_type for l in links}
    assert MapLinkType.WALKABLE in types
    assert MapLinkType.TELEPORT in types


def test_between(conn: sqlite3.Connection) -> None:
    _seed_links(conn)
    links = MapLink.between(conn, "Lumbridge", "Varrock")
    assert len(links) == 2


def test_between_with_type(conn: sqlite3.Connection) -> None:
    _seed_links(conn)
    links = MapLink.between(conn, "Lumbridge", "Varrock", link_type=MapLinkType.WALKABLE)
    assert len(links) == 2


def test_between_no_link(conn: sqlite3.Connection) -> None:
    _seed_links(conn)
    links = MapLink.between(conn, "Varrock", "Dragon Nest")
    assert len(links) == 0


def test_reachable_from(conn: sqlite3.Connection) -> None:
    _seed_links(conn)
    reachable = MapLink.reachable_from(conn, "Lumbridge")
    assert "Varrock" in reachable
    assert "Al Kharid" in reachable
    assert "Dragon Nest" in reachable
    assert len(reachable) == 3


def test_anywhere_teleport(conn: sqlite3.Connection) -> None:
    _seed_links(conn)
    links = MapLink.departing(conn, "ANYWHERE")
    assert len(links) == 1
    assert links[0].dst_location == "Varrock"
    assert links[0].link_type == MapLinkType.TELEPORT
