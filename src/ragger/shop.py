from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass

from ragger.enums import Region, ShopType
from ragger.mcp_registry import mcp_tool


@dataclass
class ShopItem:
    id: int
    shop_id: int
    item_name: str
    stock: int
    restock: int
    sell_price: int | None
    buy_price: int | None

    def asdict(self) -> dict:
        return {
            "id": self.id,
            "shop_id": self.shop_id,
            "item_name": self.item_name,
            "stock": self.stock,
            "restock": self.restock,
            "sell_price": self.sell_price,
            "buy_price": self.buy_price,
        }

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

    _COLS = "id, name, location, location_id, owner, members, region, shop_type, sell_multiplier, buy_multiplier, delta"

    def asdict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "location": self.location,
            "location_id": self.location_id,
            "owner": self.owner,
            "members": self.members,
            "region": self.region.value if self.region else None,
            "shop_type": self.shop_type.value,
            "sell_multiplier": self.sell_multiplier,
            "buy_multiplier": self.buy_multiplier,
            "delta": self.delta,
        }

    @classmethod
    def by_id(cls, conn: sqlite3.Connection, id: int) -> Shop | None:
        row = conn.execute(f"SELECT {cls._COLS} FROM shops WHERE id = ?", (id,)).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    @mcp_tool(name="ShopAll", description="List all shops, optionally filtered by region and shop_type (GENERAL, ARCHERY, SWORD, MAGIC, etc.). Returns name, location, owner, sell/buy multipliers.")
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
    @mcp_tool(name="ShopByName", description="Find a shop by exact name. Returns location, owner, members, sell/buy multipliers, and location_id for chaining with LocationByName.")
    def by_name(cls, conn: sqlite3.Connection, name: str) -> Shop | None:
        row = conn.execute(
            f"SELECT {cls._COLS} FROM shops WHERE name = ?",
            (name,),
        ).fetchone()
        return cls._from_row(row) if row else None

    @classmethod
    @mcp_tool(name="ShopSearch", description="Search shops by partial name match (LIKE %%name%%). Use when the exact shop name is unknown.")
    def search(cls, conn: sqlite3.Connection, name: str) -> list[Shop]:
        rows = conn.execute(
            f"SELECT {cls._COLS} FROM shops WHERE name LIKE ? ORDER BY name",
            (f"%{name}%",),
        ).fetchall()
        return [cls._from_row(row) for row in rows]

    _S_COLS = "s.id, s.name, s.location, s.location_id, s.owner, s.members, s.region, s.shop_type, s.sell_multiplier, s.buy_multiplier, s.delta"

    @classmethod
    @mcp_tool(name="ShopSelling", description="Find all shops that stock a given item by exact item name. Optionally filter by region. Use to answer 'where can I buy X?'")
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
    @mcp_tool(name="ShopAllAt", description="Find all shops at a location by location_id (from LocationByName). Use to see what shops are available in a town.")
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
        )

    @mcp_tool(name="ShopItems", description="Full inventory of a shop. Returns item_name, stock, restock rate, sell/buy prices. Pass the shop id from ShopByName or ShopSelling.")
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
