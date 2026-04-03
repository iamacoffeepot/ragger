import sqlite3

from ragger.enums import Region, ShopType
from ragger.shop import Shop, ShopItem


def _seed_shops(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """INSERT INTO shops (name, location, location_id, owner, members, region, shop_type, sell_multiplier, buy_multiplier, delta)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            ("Toci's Gem Store", "Aldarin", None, "Toci", 1, Region.VARLAMORE.value, ShopType.GEM.value, 1000, 700, 30),
            ("Sunset Coast General Store", "Sunset Coast", None, "Shopkeeper", 1, Region.VARLAMORE.value, ShopType.GENERAL.value, 1300, 400, 30),
            ("Fernahei's Fishing Hut", "Shilo Village", None, "Fernahei", 1, Region.KARAMJA.value, ShopType.FISHING.value, 1000, 700, 10),
        ],
    )
    conn.executemany(
        "INSERT INTO shop_items (shop_id, item_name, stock, restock, sell_price, buy_price) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, "Uncut sapphire", 3, 12000, None, None),
            (1, "Uncut emerald", 2, 24000, None, None),
            (1, "Sapphire", 3, 12000, None, None),
            (2, "Bucket", 5, 6000, None, None),
            (3, "Feather", 800, 600, None, None),
        ],
    )
    conn.commit()


def test_all(conn: sqlite3.Connection) -> None:
    _seed_shops(conn)
    shops = Shop.all(conn)
    assert len(shops) == 3
    assert all(isinstance(s, Shop) for s in shops)


def test_all_filter_region(conn: sqlite3.Connection) -> None:
    _seed_shops(conn)
    shops = Shop.all(conn, region=Region.VARLAMORE)
    assert len(shops) == 2
    assert all(s.region == Region.VARLAMORE for s in shops)


def test_all_filter_shop_type(conn: sqlite3.Connection) -> None:
    _seed_shops(conn)
    shops = Shop.all(conn, shop_type=ShopType.GEM)
    assert len(shops) == 1
    assert shops[0].name == "Toci's Gem Store"
    assert shops[0].shop_type == ShopType.GEM


def test_all_filter_region_and_type(conn: sqlite3.Connection) -> None:
    _seed_shops(conn)
    shops = Shop.all(conn, region=Region.VARLAMORE, shop_type=ShopType.GENERAL)
    assert len(shops) == 1
    assert shops[0].name == "Sunset Coast General Store"


def test_by_name(conn: sqlite3.Connection) -> None:
    _seed_shops(conn)
    shop = Shop.by_name(conn, "Toci's Gem Store")
    assert shop is not None
    assert shop.location == "Aldarin"
    assert shop.sell_multiplier == 1000
    assert shop.buy_multiplier == 700
    assert shop.region == Region.VARLAMORE


def test_by_name_not_found(conn: sqlite3.Connection) -> None:
    _seed_shops(conn)
    assert Shop.by_name(conn, "Nonexistent") is None


def test_items(conn: sqlite3.Connection) -> None:
    _seed_shops(conn)
    shop = Shop.by_name(conn, "Toci's Gem Store")
    items = shop.items(conn)
    assert len(items) == 3
    assert all(isinstance(i, ShopItem) for i in items)


def test_item_by_name(conn: sqlite3.Connection) -> None:
    _seed_shops(conn)
    shop = Shop.by_name(conn, "Toci's Gem Store")
    item = shop.item_by_name(conn, "Uncut sapphire")
    assert item is not None
    assert item.stock == 3
    assert item.restock == 12000


def test_item_by_name_not_found(conn: sqlite3.Connection) -> None:
    _seed_shops(conn)
    shop = Shop.by_name(conn, "Toci's Gem Store")
    assert shop.item_by_name(conn, "Nonexistent") is None


def test_selling(conn: sqlite3.Connection) -> None:
    _seed_shops(conn)
    shops = Shop.selling(conn, "Feather")
    assert len(shops) == 1
    assert shops[0].name == "Fernahei's Fishing Hut"


def test_selling_filter_region(conn: sqlite3.Connection) -> None:
    _seed_shops(conn)
    shops = Shop.selling(conn, "Uncut sapphire", region=Region.VARLAMORE)
    assert len(shops) == 1
    assert shops[0].name == "Toci's Gem Store"


def test_selling_not_found(conn: sqlite3.Connection) -> None:
    _seed_shops(conn)
    shops = Shop.selling(conn, "Dragon bones")
    assert len(shops) == 0


def test_effective_sell_price(conn: sqlite3.Connection) -> None:
    _seed_shops(conn)
    shop = Shop.by_name(conn, "Toci's Gem Store")
    item = shop.item_by_name(conn, "Uncut sapphire")
    # base value 25, sell_multiplier 1000 -> floor(25 * 1000 / 1000) = 25
    assert item.effective_sell_price(shop.sell_multiplier, 25) == 25


def test_effective_sell_price_markup(conn: sqlite3.Connection) -> None:
    _seed_shops(conn)
    shop = Shop.by_name(conn, "Sunset Coast General Store")
    item = shop.item_by_name(conn, "Bucket")
    # base value 2, sell_multiplier 1300 -> floor(2 * 1300 / 1000) = 2
    assert item.effective_sell_price(shop.sell_multiplier, 2) == 2


def test_effective_buy_price(conn: sqlite3.Connection) -> None:
    _seed_shops(conn)
    shop = Shop.by_name(conn, "Toci's Gem Store")
    item = shop.item_by_name(conn, "Uncut sapphire")
    # base value 25, buy_multiplier 700 -> floor(25 * 700 / 1000) = 17
    assert item.effective_buy_price(shop.buy_multiplier, 25) == 17


def test_effective_price_with_override(conn: sqlite3.Connection) -> None:
    _seed_shops(conn)
    shop = Shop.by_name(conn, "Toci's Gem Store")
    # Insert an item with manual price overrides
    conn.execute(
        "INSERT INTO shop_items (shop_id, item_name, stock, restock, sell_price, buy_price) VALUES (?, ?, ?, ?, ?, ?)",
        (shop.id, "Special gem", 1, 6000, 500, 300),
    )
    conn.commit()
    item = shop.item_by_name(conn, "Special gem")
    assert item.effective_sell_price(shop.sell_multiplier, 100) == 500
    assert item.effective_buy_price(shop.buy_multiplier, 100) == 300
