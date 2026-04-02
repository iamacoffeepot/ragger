from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass

from clogger.enums import Region


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
    owner: str | None
    members: bool
    region: Region | None
    sell_multiplier: int
    buy_multiplier: int
    delta: int

    @classmethod
    def all(
        cls,
        conn: sqlite3.Connection,
        region: Region | None = None,
    ) -> list[Shop]:
        query = "SELECT id, name, location, owner, members, region, sell_multiplier, buy_multiplier, delta FROM shops"
        params: list[int] = []

        if region is not None:
            query += " WHERE region = ?"
            params.append(region.value)

        query += " ORDER BY name"
        rows = conn.execute(query, params).fetchall()
        return [cls._from_row(row) for row in rows]

    @classmethod
    def by_name(cls, conn: sqlite3.Connection, name: str) -> Shop | None:
        row = conn.execute(
            "SELECT id, name, location, owner, members, region, sell_multiplier, buy_multiplier, delta FROM shops WHERE name = ?",
            (name,),
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    def selling(cls, conn: sqlite3.Connection, item_name: str, region: Region | None = None) -> list[Shop]:
        """Find all shops that sell a given item."""
        query = """
            SELECT DISTINCT s.id, s.name, s.location, s.owner, s.members, s.region,
                   s.sell_multiplier, s.buy_multiplier, s.delta
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
    def _from_row(cls, row: tuple) -> Shop:
        return cls(
            id=row[0],
            name=row[1],
            location=row[2],
            owner=row[3],
            members=bool(row[4]),
            region=Region(row[5]) if row[5] is not None else None,
            sell_multiplier=row[6],
            buy_multiplier=row[7],
            delta=row[8],
        )

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
