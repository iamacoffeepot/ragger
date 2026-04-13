from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass

from ragger.enums import Region, ShopType


@dataclass
class ShopItem:
    id: int
    shop_id: int
    item_name: str
    stock: int
    restock: int
    sell_price: int | None
    buy_price: int | None

    def effective_sell_price(self, sell_multiplier: int, base_value: int) -> int:
        """Calculate the actual sell price using shop multiplier and item base value."""
        if self.sell_price is not None:
            return self.sell_price
        return max(math.floor(base_value * sell_multiplier / 1000), 1)

    def effective_buy_price(self, buy_multiplier: int, base_value: int) -> int:
        """Calculate the actual buy price using shop multiplier and item base value."""
        if self.buy_price is not None:
            return self.buy_price
        return max(math.floor(base_value * buy_multiplier / 1000), math.floor(base_value * 0.1))


@dataclass
class Shop:
    id: int
    name: str
    location: str
    location_id: int | None
    owner: str | None
    members: bool
    region: Region | None
    shop_type: ShopType
    sell_multiplier: int
    buy_multiplier: int
    delta: int
    physical_currency_id: int | None
    virtual_currency_id: int | None

    _COLS = (
        "id, name, location, location_id, owner, members, region, shop_type,"
        " sell_multiplier, buy_multiplier, delta,"
        " physical_currency_id, virtual_currency_id"
    )

    @classmethod
    def all(
        cls,
        conn: sqlite3.Connection,
        region: Region | None = None,
        shop_type: ShopType | None = None,
    ) -> list[Shop]:
        query = f"SELECT {cls._COLS} FROM shops"
        params: list = []
        conditions: list[str] = []

        if region is not None:
            conditions.append("region = ?")
            params.append(region.value)
        if shop_type is not None:
            conditions.append("shop_type = ?")
            params.append(shop_type.value)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY name"
        rows = conn.execute(query, params).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> Shop | None:
        row = conn.execute(
            f"SELECT {cls._COLS} FROM shops WHERE name = ?",
            (name,),
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def search(cls, conn: sqlite3.Connection, name: str) -> list[Shop]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM shops WHERE name LIKE ? ORDER BY name",
            (f"%{name}%",),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    _S_COLS = (
        "s.id, s.name, s.location, s.location_id, s.owner, s.members,"
        " s.region, s.shop_type, s.sell_multiplier, s.buy_multiplier, s.delta,"
        " s.physical_currency_id, s.virtual_currency_id"
    )

    @classmethod
    def selling(cls, conn: sqlite3.Connection, item_name: str, region: Region | None = None) -> list[Shop]:
        """Find all shops that sell a given item."""
        query = f"""
            SELECT DISTINCT {cls._S_COLS}
            FROM shops s
            JOIN shop_items si ON si.shop_id = s.id
            WHERE si.item_name = ?
        """
        params: list = [item_name]

        if region is not None:
            query += " AND s.region = ?"
            params.append(region.value)

        query += " ORDER BY s.name"
        rows = conn.execute(query, params).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def all_at(cls, conn: sqlite3.Connection, location_id: int) -> list[Shop]:
        """Find all shops at a given location."""
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM shops WHERE location_id = ? ORDER BY name",
            (location_id,),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def _from_row(cls, row: tuple) -> Shop:
        return cls(
            id=row[0],
            name=row[1],
            location=row[2],
            location_id=row[3],
            owner=row[4],
            members=bool(row[5]),
            region=Region(row[6]) if row[6] is not None else None,
            shop_type=ShopType(row[7]),
            sell_multiplier=row[8],
            buy_multiplier=row[9],
            delta=row[10],
            physical_currency_id=row[11],
            virtual_currency_id=row[12],
        )

    def currency_name(self, conn: sqlite3.Connection) -> str | None:
        """Return the shop's currency name, or None if unknown.

        Resolves against `physical_currencies` first, then `virtual_currencies`.
        """
        if self.physical_currency_id is not None:
            row = conn.execute(
                "SELECT name FROM physical_currencies WHERE id = ?",
                (self.physical_currency_id,),
            ).fetchone()
            return row[0] if row else None
        if self.virtual_currency_id is not None:
            row = conn.execute(
                "SELECT name FROM virtual_currencies WHERE id = ?",
                (self.virtual_currency_id,),
            ).fetchone()
            return row[0] if row else None
        return None

    def items(self, conn: sqlite3.Connection) -> list[ShopItem]:
        rows = conn.execute(
            """SELECT id, shop_id, item_name, stock, restock, sell_price, buy_price
               FROM shop_items WHERE shop_id = ? ORDER BY item_name""",
            (self.id,),
        ).fetchall()
        return [ShopItem(*row) for row in rows]

    def item_by_name(self, conn: sqlite3.Connection, item_name: str) -> ShopItem | None:
        row = conn.execute(
            """SELECT id, shop_id, item_name, stock, restock, sell_price, buy_price
               FROM shop_items WHERE shop_id = ? AND item_name = ?""",
            (self.id, item_name),
        ).fetchone()
        return ShopItem(*row) if row else None
