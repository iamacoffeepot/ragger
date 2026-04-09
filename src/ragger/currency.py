"""Physical and virtual currencies.

OSRS has two distinct kinds of "currency":

- **Physical currencies** are items the player carries. They have an
  item_id (Coins, Tokkul, Trading sticks, Platinum tokens, Mark of
  grace, etc.). They can be in the inventory or bank, and many can be
  traded between players.

- **Virtual currencies** are reward counters stored as varbits or other
  player save state, with no item form. They can't be moved between
  players (Slayer reward points, Carpenter points, Void Knight
  commendation points, etc.). Each one ideally points at the varbit
  that backs it via varbit_id, though that link may be unset until the
  varbit-classification work catches up.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class PhysicalCurrency:
    id: int
    name: str
    item_id: int

    @classmethod
    def all(cls, conn: sqlite3.Connection) -> list[PhysicalCurrency]:
        rows = conn.execute(
            "SELECT id, name, item_id FROM physical_currencies ORDER BY name"
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> PhysicalCurrency | None:
        row = conn.execute(
            "SELECT id, name, item_id FROM physical_currencies WHERE name = ?",
            (name,),
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def by_item_id(cls, conn: sqlite3.Connection, item_id: int) -> PhysicalCurrency | None:
        row = conn.execute(
            "SELECT id, name, item_id FROM physical_currencies WHERE item_id = ?",
            (item_id,),
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def _from_row(cls, row: tuple) -> PhysicalCurrency:
        return cls(id=row[0], name=row[1], item_id=row[2])


@dataclass
class VirtualCurrency:
    id: int
    name: str
    varbit_id: int | None

    @classmethod
    def all(cls, conn: sqlite3.Connection) -> list[VirtualCurrency]:
        rows = conn.execute(
            "SELECT id, name, varbit_id FROM virtual_currencies ORDER BY name"
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> VirtualCurrency | None:
        row = conn.execute(
            "SELECT id, name, varbit_id FROM virtual_currencies WHERE name = ?",
            (name,),
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def _from_row(cls, row: tuple) -> VirtualCurrency:
        return cls(id=row[0], name=row[1], varbit_id=row[2])
