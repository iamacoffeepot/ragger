package dev.ragger.plugin.scripting;

import net.runelite.api.ItemComposition;
import net.runelite.client.game.ItemManager;
import party.iroiro.luajava.Lua;

/**
 * Lua binding for item lookups and pricing.
 * Exposed as the global "items" table in Lua scripts.
 */
public class ItemsApi {

    private final ItemManager itemManager;

    public ItemsApi(final ItemManager itemManager) {
        this.itemManager = itemManager;
    }

    public void register(final Lua lua) {
        lua.createTable(0, 5);

        lua.push(this::name);
        lua.setField(-2, "name");

        lua.push(this::grand_exchange_price);
        lua.setField(-2, "grand_exchange_price");

        lua.push(this::high_alchemy_price);
        lua.setField(-2, "high_alchemy_price");

        lua.push(this::base_price);
        lua.setField(-2, "base_price");

        lua.push(this::lookup);
        lua.setField(-2, "lookup");

        lua.push(this::is_stackable);
        lua.setField(-2, "is_stackable");

        lua.push(this::is_members);
        lua.setField(-2, "is_members");

        lua.setGlobal("items");
    }

    /**
     * items:name(itemId) -> string
     */
    private int name(final Lua lua) {
        final int id = (int) lua.toInteger(2);
        final ItemComposition comp = itemManager.getItemComposition(id);
        lua.push(comp.getName());
        return 1;
    }

    /**
     * items:grand_exchange_price(itemId) -> int
     */
    private int grand_exchange_price(final Lua lua) {
        final int id = (int) lua.toInteger(2);
        lua.push(itemManager.getItemPrice(id));
        return 1;
    }

    /**
     * items:high_alchemy_price(itemId) -> int
     */
    private int high_alchemy_price(final Lua lua) {
        final int id = (int) lua.toInteger(2);
        final ItemComposition comp = itemManager.getItemComposition(id);
        lua.push(comp.getHaPrice());
        return 1;
    }

    /**
     * items:base_price(itemId) -> int (store/base value)
     */
    private int base_price(final Lua lua) {
        final int id = (int) lua.toInteger(2);
        final ItemComposition comp = itemManager.getItemComposition(id);
        lua.push(comp.getPrice());
        return 1;
    }

    /**
     * items:is_stackable(itemId) -> bool
     */
    private int is_stackable(final Lua lua) {
        final int id = (int) lua.toInteger(2);
        final ItemComposition comp = itemManager.getItemComposition(id);
        lua.push(comp.isStackable());
        return 1;
    }

    /**
     * items:is_members(itemId) -> bool
     */
    private int is_members(final Lua lua) {
        final int id = (int) lua.toInteger(2);
        final ItemComposition comp = itemManager.getItemComposition(id);
        lua.push(comp.isMembers());
        return 1;
    }

    /**
     * items:lookup(itemId) -> table {name, grand_exchange_price, high_alchemy_price, base_price, stackable, members}
     */
    private int lookup(final Lua lua) {
        final int id = (int) lua.toInteger(2);
        final ItemComposition comp = itemManager.getItemComposition(id);

        lua.createTable(0, 6);

        lua.push(comp.getName());
        lua.setField(-2, "name");

        lua.push(itemManager.getItemPrice(id));
        lua.setField(-2, "grand_exchange_price");

        lua.push(comp.getHaPrice());
        lua.setField(-2, "high_alchemy_price");

        lua.push(comp.getPrice());
        lua.setField(-2, "base_price");

        lua.push(comp.isStackable());
        lua.setField(-2, "stackable");

        lua.push(comp.isMembers());
        lua.setField(-2, "members");

        return 1;
    }
}
