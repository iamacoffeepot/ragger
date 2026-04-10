import sqlite3

from ragger.enums import Region
from ragger.npc import Npc


def _seed_npcs(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO npcs (name, version, location, x, y, options, region) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("Regulus Cento", "Misthalin", "Misthalin", 3281, 3413, "Talk-to, Travel", Region.MISTHALIN.value),
            ("Regulus Cento", "Varlamore", "Varlamore", 1700, 3143, "Talk-to, Travel", Region.VARLAMORE.value),
            ("Aubury", "Normal", "Varrock", 3253, 3401, "Talk-to, Teleport, Trade", Region.MISTHALIN.value),
            ("Hans", None, "Lumbridge", 3212, 3219, "Talk-to, Age", Region.MISTHALIN.value),
        ],
    )
    conn.commit()


def test_all(conn: sqlite3.Connection) -> None:
    _seed_npcs(conn)
    npcs = Npc.all(conn)
    assert len(npcs) == 4


def test_all_filter_region(conn: sqlite3.Connection) -> None:
    _seed_npcs(conn)
    npcs = Npc.all(conn, region=Region.VARLAMORE)
    assert len(npcs) == 1
    assert npcs[0].name == "Regulus Cento"
    assert npcs[0].version == "Varlamore"


def test_by_name(conn: sqlite3.Connection) -> None:
    _seed_npcs(conn)
    npc = Npc.by_name(conn, "Regulus Cento")
    assert npc is not None
    assert npc.name == "Regulus Cento"


def test_by_name_with_version(conn: sqlite3.Connection) -> None:
    _seed_npcs(conn)
    npc = Npc.by_name(conn, "Regulus Cento", version="Varlamore")
    assert npc is not None
    assert npc.version == "Varlamore"


def test_all_by_name(conn: sqlite3.Connection) -> None:
    _seed_npcs(conn)
    npcs = Npc.all_by_name(conn, "Regulus Cento")
    assert len(npcs) == 2
    versions = {n.version for n in npcs}
    assert "Misthalin" in versions
    assert "Varlamore" in versions


def test_by_name_single(conn: sqlite3.Connection) -> None:
    _seed_npcs(conn)
    npc = Npc.by_name(conn, "Hans")
    assert npc is not None
    assert npc.location == "Lumbridge"


def test_search(conn: sqlite3.Connection) -> None:
    _seed_npcs(conn)
    npcs = Npc.search(conn, "Regulus")
    assert len(npcs) == 2


def test_with_option(conn: sqlite3.Connection) -> None:
    _seed_npcs(conn)
    npcs = Npc.with_option(conn, "Travel")
    assert len(npcs) == 2
    assert all(n.name == "Regulus Cento" for n in npcs)


def test_with_option_and_region(conn: sqlite3.Connection) -> None:
    _seed_npcs(conn)
    npcs = Npc.with_option(conn, "Teleport", region=Region.MISTHALIN)
    assert len(npcs) == 1
    assert npcs[0].name == "Aubury"


def test_at_location(conn: sqlite3.Connection) -> None:
    _seed_npcs(conn)
    npcs = Npc.at_location(conn, "Varrock")
    assert len(npcs) == 1
    assert npcs[0].name == "Aubury"


def test_has_option(conn: sqlite3.Connection) -> None:
    _seed_npcs(conn)
    npc = Npc.by_name(conn, "Aubury")
    assert npc.has_option("Teleport")
    assert npc.has_option("Trade")
    assert not npc.has_option("Travel")


def test_option_list(conn: sqlite3.Connection) -> None:
    _seed_npcs(conn)
    npc = Npc.by_name(conn, "Aubury")
    options = npc.option_list()
    assert "Talk-to" in options
    assert "Teleport" in options
    assert "Trade" in options
