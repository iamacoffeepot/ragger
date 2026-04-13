### Shop (`src/ragger/shop.py`)

```python
from ragger.shop import Shop, ShopItem

Shop.all(conn, region?, shop_type?) -> list[Shop]
Shop.by_name(conn, name) -> Shop | None
Shop.search(conn, name) -> list[Shop]              # partial name match
Shop.selling(conn, item_name, region?) -> list[Shop]
Shop.all_at(conn, location_id) -> list[Shop]
shop.items(conn) -> list[ShopItem]
shop.item_by_name(conn, item_name) -> ShopItem | None
shop.location_id -> int | None                        # FK to locations table
shop.shop_type -> ShopType
shop.sell_multiplier -> int                            # permille (1000 = 100%)
shop.buy_multiplier -> int
shop.delta -> int                                      # price change per stock unit
shop.physical_currency_id -> int | None                # FK to physical_currencies
shop.virtual_currency_id -> int | None                 # FK to virtual_currencies
shop.currency_name(conn) -> str | None                 # resolves whichever side is set
item.effective_sell_price(sell_multiplier, base_value) -> int
item.effective_buy_price(buy_multiplier, base_value) -> int
```
